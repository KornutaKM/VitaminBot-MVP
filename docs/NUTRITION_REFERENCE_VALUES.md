# KIR-115 EU / EFSA Reference Values

KIR-115 is the versioned scientific-reference boundary for the EU-oriented VitaminBot MVP.

Dataset version: eu-efsa-mvp-2026-09-20.v1

The implementation is derived only from the accepted KIR-127 authoritative EU-first dossier,
its controlled 2026 DHA erratum, and the independent KIR-153 / KIR-154 validation gates.

## Core contract

Reference categories remain typed:

- NRV
- AR
- PRI
- AI
- RI
- UL
- SAFE_LEVEL

They are not aliases and are never collapsed into a generic daily value.

A UL is a safety reference, not a target or personalized dose. A SAFE_LEVEL is a different
reference type and never aliases UL.

Absence of a numeric reference is machine-readable data. Examples include:

- vitamin C: no adequate data to derive a UL;
- vitamin B12: no numeric UL / no defined adverse effects;
- pediatric calcium: no adequate data to derive a UL;
- iron: no UL, with separate SAFE_LEVEL records;
- long-chain omega-3 contexts: no UL established.

A missing numeric value never means zero, infinity, or unlimited.

## Provenance and versioning

Every reference record binds to an immutable source record containing:

- authority;
- jurisdiction;
- source family;
- stable external identifier such as DOI, CELEX, or official document ID;
- source URL;
- adopted/published/amended dates when available;
- source version label;
- retrieval date;
- lifecycle state.

Every numeric runtime result exposes the exact reference record ID, reference type, value/unit,
exposure basis, source key, source version, and dataset version.

The dataset supports supersession fields without automatic source monitoring. External source
monitoring remains outside KIR-115; future change signals must create review candidates rather
than mutate governed scientific truth automatically.

## Population and applicability

Population matching preserves source-native boundaries in months and supports:

- sex;
- general / pregnancy / lactation life stage;
- premenopausal / postmenopausal condition.

Missing required dimensions return indeterminate. A different known dimension returns
not_applicable. There is no fallback to an adult profile.

Conditional references remain conditional. In particular:

- adult zinc AR/PRI requires an explicit dietary phytate value;
- vitamin D AI requires the source assumption of minimal cutaneous synthesis;
- iron SAFE_LEVEL excludes individuals receiving iron under medical supervision;
- restricted safety records require their exact exposure basis.

## Amount semantics

Reference records preserve canonical VitaminBot amount semantics.

Examples:

- folate DRVs use an explicit dietary-folate-equivalent basis;
- supplemental-folate UL records use a separate supplemental-folate analyte;
- vitamin-D UL records use the EFSA VDE equivalence basis;
- fish-oil material is not DHA;
- EPA+DHA combined is not DHA alone.

Comparison accepts canonical ComputedAmount values on a PER_DAY basis. Compatible metric
mass units are converted only through the accepted KIR-113 mass converter.

Increment and range-increment records are intentionally not compared as absolute totals.
Pregnancy/lactation additions therefore cannot silently become point-valued absolute references.

## Comparison semantics

Comparison results can state only the neutral relation:

- below
- equal
- above

The result always withholds a personal safety conclusion. The API has no safe, unsafe, toxic,
recommended, maximum-for-you, or dose-prescription state.

Non-numeric references return NO_NUMERIC_REFERENCE rather than manufacturing a threshold.

## EFSA 2026 DHA safety semantics

The controlling narrow source is:

EFSA NDA Panel (2026), Scientific Opinion on the tolerable upper intake level for supplemental
docosahexaenoic acid, DOI 10.2903/j.efsa.2026.9858.

For the source-defined supplemental / added DHA-alone or mostly-DHA exposure:

- no UL is established;
- a separate SAFE_LEVEL record is 1 g/day;
- SAFE_LEVEL is not UL, target, prescribed dose, or personal maximum;
- EPA/DHA must be strictly less than 0.3;
- both EPA and DHA amounts must be known;
- qualifying source classes are fish-oil concentrates, algal oil, and krill oil;
- represented forms are triacylglycerol, ethyl ester, and phospholipid;
- background dietary DHA must not be included in the compared amount;
- mixed qualifying/nonqualifying exposure returns partial coverage rather than a complete
  assessment.

Generic fish oil, generic omega-3, and generic EPA+DHA do not inherit the DHA-specific
SAFE_LEVEL.

The 2012 long-chain n-3 PUFA safety record remains available under its exact record ID. For the
exact qualifying 2026 DHA scope, the 2026 records have narrow selection precedence. This
preserves historical reproducibility without silently rewriting the 2012 source.

## Stale-result invalidation

Lookup applicability and comparison results preserve:

- dataset version;
- exact record ID;
- source version;
- the immutable caller-supplied context revision used by the original ReferenceQuery.

The context revision is bound at lookup time. Comparison inherits that binding from LookupResult.
A caller may repeat the same revision explicitly, but attempting to relabel an old lookup with a
different product/formulation/source revision is rejected.

comparison_is_stale() invalidates a prior result when the scientific dataset version changes,
the referenced record/source is no longer active, or the caller's product/formulation/source
context revision changes.

This is the KIR-115 data-layer guard against silently reusing a result after product
reformulation or scientific-source version change.

## Dataset coverage

The first dataset contains EU/EFSA records for the MVP classes defined by KIR-127:

- vitamin D;
- vitamin C;
- magnesium;
- zinc;
- selenium;
- vitamin B6;
- vitamin B12;
- folate / folic acid with DFE and supplemental-form separation;
- iron;
- calcium;
- EPA+DHA / DHA.

EU Annex XIII labelling NRVs remain separate from EFSA dietary references and safety records.

## Non-goals

KIR-115 does not implement:

- personalized dose recommendations;
- diagnosis or toxicity classification;
- scheduling / interaction rules;
- KIR-119 compatibility rules;
- automatic scientific-source monitoring;
- LLM-authored scientific constants;
- cross-jurisdiction fallback;
- compound-to-elemental inference;
- generic IU-to-mass conversion.

All scientific numeric constants in this module are traceable to the accepted KIR-127 source
dossier and its accepted DHA correction.
