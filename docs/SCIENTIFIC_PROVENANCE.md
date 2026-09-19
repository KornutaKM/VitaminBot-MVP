# Scientific Provenance

This document defines repository-level provenance expectations. It does **not** define nutrient doses, safety thresholds, medical rules, or scientific constants.

## Authority

Scientific and safety-critical values must come from explicitly governed source material. LLM output is not an authoritative source for numeric medical decisions, dose calculations, or threshold comparisons.

## Required provenance for future scientific data

Any future scientific or safety-critical value should be representable with enough metadata to identify:

- the source or issuing authority;
- the source title or stable reference;
- the applicable population/context;
- units and measurement semantics;
- version, publication date, or effective date when relevant;
- retrieval/verification date when relevant;
- limitations, exclusions, or applicability constraints;
- the Linear issue or review that introduced or changed the governed value.

The exact domain schema belongs to the engineer/task assigned to define that contract.

## Fail-closed expectation

When a safety-critical decision depends on missing, conflicting, stale, ambiguous, or non-applicable governed data, the application must not invent a numeric substitute. The safe behavior is to withhold the numeric decision and surface the validation/provenance problem for governed handling.

## Change control

Changes to governed scientific or safety-critical data require explicit review under the relevant Linear scope. Application engineers may implement storage, transport, validation plumbing, or deterministic evaluation only when the governing contract and source are available.
