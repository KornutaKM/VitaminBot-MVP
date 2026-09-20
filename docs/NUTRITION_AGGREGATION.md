# KIR-114 Daily Nutrition Aggregation

KIR-114 aggregates confirmed planned daily contributions while preserving KIR-109/KIR-113 identity, basis, provenance, and fail-closed boundaries.

It never infers consumed intake and does not implement reference-value, safety, scheduling, recommendation, compound-to-elemental, fish-oil-to-EPA/DHA, or generic IU conversion logic.

## Input

Resolved numeric inputs must already be `PER_DAY` KIR-113 `ComputedAmount` values with a matching `planned_daily_normalization` plan ID/version trace.

Unresolved KIR-113 outcomes remain unresolved contributors. They are never converted to zero.

## Aggregate compatibility

Amounts share one total only when subject kind, subject ID, amount basis, equivalence basis, and unit dimension match.

Mass is normalized exactly to micrograms with KIR-113 `convert_mass`.

Non-mass contributions must already use the exact same unit. KIR-114 does not perform scientific or generic non-mass conversion.

## Exact arithmetic

No floats are used.

Totals are summed through exact `Fraction` values and reconstructed into exact terminating `Decimal` values. Ambient Decimal precision/rounding settings therefore cannot change a total.

There is no implicit aggregation rounding policy.

## Duplicate behavior

Source ID alone is never a deduplication key.

An exact repeated logical contribution requires the same tracked instance, formulation, plan/version, aggregate semantics, source amount lineage, source provenance, source serving lineage, and planned-daily trace identity. Identical repeats count once and are explicitly flagged.

If that same logical identity carries conflicting values or material provenance, no winner is selected and the affected total is withheld.

Distinct tracked instances/plans that happen to share source lineage are all counted. Shared lineage is informational provenance only.

## Incomplete totals

If a relevant contributor remains unresolved, the known resolved subtotal can be returned but `is_complete` is false and `UNRESOLVED_CONTRIBUTOR` is explicit.

A conflict or incompatible non-mass unit set yields no numeric total for the affected aggregate key.

## Traceability

Every counted contribution retains product, formulation, tracked instance, contribution ID, confirmation ref, plan ID/version, normalized value/unit, original source amount/source/basis lineage, computation traces, chemical form, and equivalence basis.

## Non-goals

No NRV/AR/PRI/AI/UL/SAFE_LEVEL comparison.

No personalized dose.

No interaction or scheduling rule.

No recommendation or diagnosis.

No persistence migration.