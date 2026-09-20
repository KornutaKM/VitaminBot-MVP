# KIR-118 Barcode/QR catalog lookup

## Scope

This module implements the ENG3 discovery boundary for barcode, GTIN, and GS1 Digital Link input:

`raw scan -> local identifier parse -> provider-neutral lookup -> external_unverified candidate -> explicit identity confirmation or photo/manual fallback`

It does **not** create confirmed nutrition facts, choose a production catalog provider, store provider credentials, define scientific conversions, or implement Telegram UI.

## Local identifier parsing

`parse_lookup_request()` runs before any remote lookup.

Supported local identifier forms:

- GTIN-8;
- GTIN-12 / UPC representation;
- GTIN-13 / EAN representation;
- GTIN-14;
- GS1 Digital Link URI carrying AI `01`.

The raw scan is preserved exactly. A normalized lookup identifier is stored separately.

GTIN check digits are validated locally. An invalid check digit or unrecognized identifier fails closed to photo/manual entry without calling a catalog provider.

For GS1 Digital Link the request preserves:

- raw URI;
- extracted GTIN;
- primary key as `01:<gtin>`;
- path/query qualifiers as raw AI/key-value pairs;
- scan kind and scan timestamp.

Qualifiers such as lot, serial, or date-like AIs are preserved as observations. Their presence does not create scientific or formulation truth.

## Provider-neutral boundary

A `CatalogLookupProvider` exposes provider metadata plus one lookup method. Provider ordering is constructor configuration, not business logic.

The project-owned result contract includes:

- provider key and provider class;
- exact adapter version;
- query mode and queried identifier;
- retrieval timestamp;
- result state;
- response hash/reference;
- license/rights metadata;
- zero or more catalog candidates.

Supported provider result states are:

- `no_match`;
- `single_exact_match`;
- `multiple_matches`;
- `partial_match`;
- `provider_unavailable`;
- `rate_limited`;
- `access_denied`;
- `malformed_response`.

Expected provider failures do not block supplement entry. The service may continue to the next configured provider; otherwise it routes to photo/manual entry.

## Candidate trust model

Every provider field is a `SourcedCandidateField` and defaults structurally to:

`verification_state = external_unverified`

The field retains:

- raw provider value;
- optional normalized candidate;
- provider key;
- provider record ID when supplied;
- source path/attribute;
- retrieval timestamp;
- provider record timestamp when supplied;
- source URL when supplied;
- license class / rights note;
- explicit conflict list.

A provider adapter has no representation that can mark one of these fields `user_confirmed` or `label_confirmed`.

An exact GTIN match may accelerate identity discovery. It never:

- confirms serving size;
- confirms ingredient/nutrient quantities;
- resolves compound-vs-elemental meaning;
- proves the current formulation;
- bypasses photo/manual label confirmation.

`CatalogDiscoveryOutcome.nutrition_confirmation_required` is therefore always true.

## Identity versus nutrition

The discovery service separates two decisions:

1. **Identity discovery** — “is this likely the product/package?”
2. **Label/nutrition confirmation** — “what does the current physical label actually say?”

A clean single exact catalog candidate routes to `confirm_identity`.

Even after identity confirmation, nutrition/serving facts still require the KIR-117 label-photo confirmation path or KIR-116 manual path.

## Project-owned candidate identity

Provider record IDs are provenance, not concurrency authority.

For each discovery result the service derives a versioned project-owned candidate fingerprint from:

- lookup request ID;
- normalized scanned identifier;
- provider identity;
- exact sourced candidate fields;
- freshness/conflict state;
- image references/rights metadata.

This gives the application an auditable candidate identity without treating provider IDs as globally trustworthy.

## Freshness policy

KIR-128 deliberately defines no universal “N days old = stale” threshold, and KIR-118 does not invent one.

Freshness is explicit metadata:

- `provider_timestamp_current_unknown_semantics`;
- `provider_timestamp_missing`;
- `catalog_label_conflict`;
- `possible_old_package`;
- `provider_marks_obsolete`;
- `freshness_unresolved`.

A provider timestamp can be preserved without being interpreted as proof of a current formulation.

`partial_match`, an `incomplete_record` provider quality flag, or any unresolved/stale freshness state routes to photo/manual confirmation.

## Multiple matches

Multiple materially distinct candidates are never auto-ranked into acceptance.

The outcome is `catalog_ambiguous`, candidates remain separate with provenance, and the flow routes to photo/manual resolution.

The service also rejects duplicate field names inside one candidate instead of silently selecting one provider value.

## Current-label conflict

The caller may supply already confirmed current-label facts solely for conflict detection.

Comparison is representation-only: whitespace/case normalization is allowed, but KIR-118 performs no unit conversion, dose inference, or scientific equivalence.

If a catalog field conflicts with confirmed current-label evidence:

- both values remain preserved;
- the catalog field receives `catalog_label_conflict`;
- the candidate receives the same conflict;
- freshness becomes `catalog_label_conflict`;
- the outcome routes to photo/manual resolution;
- the catalog value remains `external_unverified`;
- the confirmed label fact is never overwritten.

This is package-evidence precedence, not scientific authority.

## No match and provider failure

`no_match` is a normal outcome.

If all successfully queried providers return no match, the discovery state is `no_catalog_match`.

If the provider chain cannot complete because of outage, rate limiting, access denial, malformed output, or no configured provider, the state is `lookup_degraded`.

Both routes provide:

- KIR-117 label photo;
- KIR-116 manual entry.

The scanned identifier remains available to the application for future retry/provenance. The module never synthesizes catalog facts.

## Image candidates and rights

Catalog images are discovery evidence only.

Each `ImageCandidate` retains:

- provider;
- related identifier/record;
- retrieval timestamp;
- role when supplied;
- rights note;
- cache/display permission state;
- package-match state.

Unknown rights remain `unknown`; the module never assumes an image may be cached or redistributed.

## Provider payload retention

The canonical contract stores a response hash/reference, not an unrestricted raw provider payload.

A concrete provider adapter must obey its provider-specific retention/license terms. KIR-118 does not create a hidden durable raw-payload store.

## Mocked integration coverage

`tests/test_catalog_lookup.py` covers:

- valid GTIN-8/12/13/14 parsing;
- invalid check-digit fail-closed behavior;
- GS1 Digital Link qualifier preservation;
- exact match remaining external-unverified;
- multiple-match ambiguity;
- stale/incomplete routing;
- no invented age threshold;
- current-label/catalog conflict;
- no-match fallback;
- rate-limit fall-through to a second provider;
- provider outage;
- malformed provider-contract output;
- field-level provenance and image-rights preservation;
- exact identifier preservation;
- duplicate candidate fields;
- Digital Link provider query mode.

No test treats catalog nutrition agreement as label truth.

## Production integration requirements

Before enabling a live catalog provider:

1. implement the provider behind `CatalogLookupProvider`;
2. record exact adapter/provider API revision where available;
3. document credentials, quotas, rate-limit handling, and retry policy outside candidate truth;
4. confirm license/caching/display/image rights;
5. retain provider response only as permitted;
6. measure Finland supplement coverage instead of inferring it from global provider counts;
7. keep photo/manual flow operational when the provider has zero hits or is unavailable.

## Explicit non-goals

KIR-118 does not decide:

- which catalog is the production winner;
- whether a product is safe or appropriate;
- serving/nutrient confirmation;
- compound-to-elemental equivalence;
- IU-to-mass conversion;
- dose, UL, or reference values;
- interaction severity;
- immutable formulation identity from GTIN;
- scientific meaning from a catalog field.
