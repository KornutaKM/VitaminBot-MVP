# KIR-121 Independent Safety Regression Suite

## Purpose

This suite is the ENG4 independent regression gate for VitaminBot nutrition safety behavior.

It is derived from accepted KIR-126, KIR-110, KIR-129, KIR-144 and KIR-153 safety contracts and source semantics. It is intentionally separate from ENG2 implementation test files.

## Covered safety boundaries

The dedicated suite covers, at minimum:

- mg vs microgram order-of-magnitude protection;
- rejection of generic IU-to-mass conversion;
- Vitamin D IU conversion requiring confirmed supported chemical form;
- compound/material mass remaining separate from elemental/analyte mass;
- fish-oil material remaining separate from EPA and DHA;
- retry/double-count protection without deduplicating genuinely distinct products;
- unresolved contributors remaining explicit rather than becoming zero;
- missing age/applicability failing closed;
- UL vs SAFE_LEVEL/no-UL semantics;
- EFSA B6 final established UL vs intermediate derivation;
- DHA EPA/DHA applicability boundary and generic-fish-oil exclusion;
- below-reference comparison not becoming personal safety clearance;
- exact iron/zinc threshold semantics without display rounding;
- fortified-food iron excluded from the supplemental-iron scheduling rule;
- calcium carbonate/citrate/unknown-form separation;
- null separation gap preservation;
- fixed-combination products never being logically split;
- broad ethyl-ester omega-3 scheduling remaining disabled;
- calcium split-event preference rearranging only existing schedulable units;
- high-risk medication context withholding generic scheduling;
- user routine preference remaining user provenance, not scientific provenance;
- stale scheduling results after context revision changes.

## Independence rule

Expected values and states in this file are taken from the accepted ENG4 safety contracts and controlling source semantics.

The suite must not:

- import expected values from production rule tables;
- inspect a production rule definition and assert that the implementation returns the same value;
- reinterpret an ENG2 unit test as independent evidence;
- weaken an expected safety state to fit current implementation.

Using public production APIs is required because the suite validates the production boundary. Expected behavior remains independently specified.

## CI gate

The GitHub Actions job **Safety regression — ENG4 independent suite** runs on every pull request and push to main.

It is blocking: it has no continue-on-error behavior.

The job runs:

```text
pytest -q tests/test_safety_regression_kir121.py
```

This job complements, rather than replaces, the normal Linux lint/type/full-test job.

## Release rule

A failure in this suite on a Safety Critical release candidate blocks release until the owning implementation lane fixes the behavior and ENG4 independently retests the exact corrected head.

Green general CI does not override a failing ENG4 safety regression.

## Residual limitations

This initial suite validates the currently implemented deterministic normalization, aggregation, reference and scheduling-rule boundaries.

It does not claim complete validation of:

- future medication-interaction databases;
- future LLM/localization rendering implementations;
- future OCR provider behavior beyond the canonical confirmed-data boundary;
- future emergency/acute-symptom routing;
- reference substances or rules not present in the accepted MVP contracts;
- full end-to-end Telegram presentation, which requires downstream integration validation.

Those paths remain subject to their own ENG4 contracts and must fail closed until independently covered.
