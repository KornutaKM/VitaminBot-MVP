# KIR-117 Label-photo extraction pipeline

## Scope

This module implements the ENG3 recognition boundary for a single uploaded supplement-label image:

`transient image -> provider adapter -> KIR-111 candidate -> explicit user confirmation/edit -> confirmed-record sink`

It does **not** select a production OCR provider, implement barcode/catalog lookup, define scientific conversions, change PostgreSQL schema, or implement Telegram UI. Those boundaries remain owned by their existing tasks/contracts.

## Trust model

The pipeline preserves the KIR-111 separation between observation, candidate, confirmation, and downstream scientific resolution.

A `RecognitionProvider` may only return a `LabelExtraction` in `extracted_unconfirmed`. The pipeline rejects provider output that:

- uses a non-photo acquisition method;
- carries a confirmation revision;
- marks any field confirmed/corrected/rejected;
- changes/adds source assets instead of preserving the pipeline-owned transient source;
- contains duplicate confirmation field IDs;
- otherwise violates the KIR-111 contract.

The pipeline, not the provider, computes the next review state:

- no attention requirement -> `ready_for_user_confirmation`;
- ambiguity, low/unknown confidence, unreadability, or other KIR-111 attention requirement -> `user_resolution_required`.

Provider confidence is preserved as metadata and cannot bypass confirmation.

## Mandatory confirmation

`confirm_and_persist()` is revision-bound and field-complete:

- `expected_revision` must equal the candidate revision;
- the displayed field-ID set must exactly equal the candidate field set;
- every displayed field needs exactly one explicit decision;
- visible fields may be confirmed or corrected;
- absent/unreadable/unknown fields use explicit `confirm_unknown` rather than pretending a value exists;
- correction keeps the original raw text in `CorrectionRecord` and discards provider normalization/confidence for the edited field;
- any rejected field rejects the capture;
- only the reconstructed `accepted_for_storage` record crosses the `ConfirmedLabelSink` boundary.

The sink contract is idempotent by `extraction_id:confirmation_revision`. The pipeline deletes source pixels only after successful persistence. If persistence fails, the transient source remains available until TTL expiry so a safe retry is possible.

An `accepted_for_storage` record may still contain semantically unresolved fields with `blocked_unresolved`; user confirmation means the transcription matches the package, not that the value is scientifically resolved or safe.

## Privacy and image lifecycle

KIR-137 requires raw user label images to be transient by default. KIR-117 therefore uses a **30-minute maximum processing TTL** and permits earlier deletion.

Deletion happens on:

- successful confirmed-record persistence;
- explicit reject/abandon;
- provider execution failure routed to manual entry;
- provider contract failure routed to manual entry;
- automatic expiry.

Confirmation also re-checks source availability. If the image expired while the user was reviewing, the pipeline returns `manual_entry_required` / `source_expired`; it does not persist stale model output as if the source were still inspectable.

`InMemoryTransientImageStore` exists only for tests/local wiring. It does not survive process termination and therefore is **not** a production TTL mechanism. A production storage adapter must enforce automatic expiry independently of application-process lifetime (for example storage-native lifecycle/TTL), implement idempotent deletion, and avoid raw image URLs/content in normal logs.

Long-lived provenance stores the content hash, timestamps, provider/model/adapter/prompt/schema/preprocessing revisions, and KIR-111 raw/structured observations. It does not store the provider's complete raw response; only an optional SHA-256 reference is carried by this implementation.

## Failure behavior

The pipeline fails closed to `manual_entry_required` for:

- source expiry;
- provider timeout/unavailability represented by `ProviderExecutionError`;
- malformed/provider-contract-invalid output.

It never invents missing dosage facts and never substitutes a plausible value. A future multi-provider orchestrator may try another authorized adapter before manual fallback, but that is not implicit in this module.

## Provider-neutral adapter boundary

A provider adapter receives:

- image bytes;
- MIME type;
- the project-owned transient `SourceAsset`.

It returns:

- a KIR-111 `LabelExtraction` candidate;
- `ProviderRevision` with provider/model/adapter/prompt/schema/preprocessing revisions;
- optional raw-provider-response SHA-256.

Provider-native objects are adapter-local and must not become canonical product records.

## Benchmark harness and corpus gate

`vitaminbot.recognition.benchmark` implements a KIR-147-compatible frozen manifest loader and scorer. Every case has:

- source class and rights state;
- external-provider processing permission;
- content hashes for image and gold annotation;
- split/group metadata for leakage controls;
- safety-significant field-role mapping.

The scorer reports separately:

- schema validity;
- raw-label-text fidelity;
- missing fields;
- hallucinated fields;
- field raw-text and normalized-candidate mismatches;
- missing source regions;
- quantity/unit/serving-basis/chemical-form errors;
- expected routing-state match;
- abstention correctness;
- estimated manual correction burden.

No aggregate acceptance threshold or production provider winner is encoded.

The repository includes a two-case **smoke corpus v0.1.0** using project-owned synthetic fixtures. It exercises Vitamin D IU preservation and ambiguous magnesium compound-vs-elemental abstention. Its manifest sets `provider_benchmark_eligible=false`, so the harness explicitly refuses to treat it as production-provider selection evidence. A real provider comparison must first freeze the full KIR-147-compatible corpus/gold revision with required rights, adjudication, duplicate controls, and adversarial inventory.

## Operational integration requirements

Before a production provider is enabled, integration must additionally provide:

1. a production transient store with storage-native <=30-minute automatic expiry;
2. an authorized provider configuration satisfying Project Control privacy/region gates;
3. an idempotent durable `ConfirmedLabelSink` owned by the persistence/application boundary;
4. the complete frozen KIR-147 provider-benchmark corpus rather than the smoke corpus;
5. exact provider/model/prompt/schema/preprocessing revision recording;
6. a user-visible confirmation/edit surface that presents the full confirmed scope and source evidence while it exists;
7. manual entry/re-upload handling for expired or failed captures.

## Explicit non-goals

This implementation does not decide:

- compound-to-elemental equivalence unless literally printed;
- IU-to-mass conversion;
- nutrient reference values/ULs;
- dose appropriateness;
- interactions or safety severity;
- current catalog formulation;
- which OCR/VLM provider is the production winner.
