# KIR-111 Product-label recognition contract

Schema version: `1.0.0`.

This module implements the accepted KIR-125 recognition/confirmation contract on top of the
KIR-109 canonical nutrition-domain boundary. It deliberately does not add scientific conversion,
reference values, safety classification, or recommendation logic.

## State separation

The recognition layer keeps these states distinct:

1. raw observation;
2. extracted/structured candidate;
3. normalized candidate;
4. user confirmation/correction;
5. scientific semantic resolution.

Confidence is metadata used for attention routing. It is never authority to auto-confirm a field.

Photo, barcode/catalog, and manual acquisition share the same candidate/confirmation contract.
Provider-specific response objects must remain adapter-local.

## Versioned extraction envelope

`LabelExtraction` contains:

- acquisition method;
- source assets;
- complete raw label text;
- product identity candidate;
- optional serving observation;
- ordered nutrient/ingredient rows;
- ambiguity markers;
- record state;
- confirmation revision.

Unknown schema versions fail validation.

The confirmation/ambiguity state machine allows:

`capture_received`
→ `extracted_unconfirmed`
→ `ready_for_user_confirmation` or `user_resolution_required`
→ `accepted_for_storage`

Any review point may instead route to `manual_entry_required` or `rejected`.

There is intentionally no direct
`extracted_unconfirmed → accepted_for_storage` transition.

An accepted record requires a positive confirmation revision and every retained field must be in
an explicit accepted state: `user_confirmed`, `user_corrected`, or
`user_confirmed_unknown`. Rejected and unconfirmed fields cannot satisfy whole-record
acceptance. A rejected field is never a downstream normalization candidate and continues to route
attention until the record is resolved.

A literal user-confirmed field may still remain semantically unresolved; such a field stays
`blocked_unresolved` for downstream scientific use.

## Evidence and provenance

`SourceAsset` identifies the acquisition source without storing image bytes in the canonical
recognition record. `SourceRegion` points to the supporting image/page/region.

This is compatible with KIR-137: production raw label images are transient by default. Durable
recognition evidence is structured text + source metadata + confirmation/correction history.
If expired visual evidence is needed later, request re-upload.

Each `FieldObservation` preserves:

- exact raw text;
- optional normalized candidate;
- source kind;
- presence state;
- source regions;
- confidence metadata;
- ambiguity codes;
- confirmation state;
- semantic state;
- downstream eligibility;
- correction history.

Normalization never erases raw text.

## Confidence

`ConfidenceMetadata` supports a qualitative band plus optional provider-native raw score/scale.

No confidence threshold promotes a candidate to truth.

Low/unknown-confidence unconfirmed fields route attention. High-confidence fields remain
`unconfirmed` until an explicit user confirmation/correction.

## Fail-closed ambiguity

Supported ambiguity codes include:

- low-confidence text;
- conflicting observations;
- missing serving information;
- compound-vs-elemental unclear;
- unit unclear;
- row relationship unclear;
- reference-value unclear;
- source-region incomplete;
- catalog conflicts with label;
- unreadable text.

Semantically unresolved fields/rows must be `blocked_unresolved`.

### Compound versus elemental

The row:

`Magnesium Citrate 500 mg`

may be transcribed and structurally parsed, but it does not establish that `500 mg` is elemental
magnesium. The contract allows the literal row while requiring
`compound_vs_elemental_unclear`, `semantic_state=unresolved`, and no explicit equivalent
amount.

`ExplicitEquivalentObservation` is allowed only when the source explicitly states the
relationship, for example:

`Magnesium citrate 500 mg, providing magnesium 80 mg`

Recognition records that wording; it does not calculate it.

## Serving semantics

Recognition does not collapse:

- per capsule;
- per serving/label portion;
- manufacturer-recommended daily portion.

Missing serving information remains missing/unresolved. Recognition does not derive it from
package count or suggested use.

## External catalog boundary

`SourceKind.EXTERNAL_CATALOG` lets KIR-118 converge barcode/catalog acquisition into the same
candidate shape.

KIR-128 remains controlling:

- catalog fields are external-unverified by default in the adapter layer;
- exact GTIN can accelerate identity discovery but does not prove current formulation;
- provider adapters cannot write directly to confirmed nutrition state;
- catalog/label conflicts preserve both provenance records;
- no silent overwrite, averaging, or plausibility selection.

KIR-111 does not select a catalog provider.

## Golden fixtures

Synthetic fixtures cover the accepted KIR-125 Golden A–F behavior:

- Magnesium + B6;
- Vitamin D in IU;
- fish oil / total omega-3 / EPA / DHA;
- ambiguous `Magnesium Citrate 500 mg` that must fail closed;
- conflicting label regions that preserve both values without selecting a winner;
- missing serving information that preserves the visible amount while blocking basis-dependent
  downstream use.

They contain no user data.

## Executable validation invariants

The contract rejects:

- unsupported schema versions;
- present fields without raw source text;
- normalized candidates without raw text;
- semantically unresolved fields exposed downstream;
- user-corrected fields without correction history;
- source regions referencing unknown assets;
- ready-for-confirmation records hiding attention-required fields;
- accepted records without explicit confirmation revision;
- accepted records containing rejected or unconfirmed fields;
- rejected fields remaining downstream normalization candidates;
- direct auto-accept state transitions;
- compound/elemental ambiguity combined with a claimed explicit equivalent amount.

## Downstream ownership

KIR-109 remains canonical for scientific/domain semantics.

Recognition never:

- invents elemental quantity from compound mass;
- derives EPA/DHA from fish-oil mass;
- converts IU to mass;
- treats unknown as zero;
- chooses scientific meaning because confidence is high;
- treats a catalog match as current-label truth;
- performs final safety classification.

KIR-117 may implement OCR/vision extraction against this contract. KIR-118 may implement catalog
adapters against the same candidate boundary.
