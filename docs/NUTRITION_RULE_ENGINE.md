# KIR-119 — Evidence-backed compatibility and scheduling rule engine

KIR-119 is the deterministic scientific-rule boundary between confirmed VitaminBot intake data
and later planning/presentation layers.

It implements only the rule subset independently accepted by KIR-144 from the KIR-143 evidence
dossier. It does not create personalized doses, diagnose interactions, or assign biological
Morning / Day / Evening superiority.

Ruleset version: `kir-119-2026-09-20.v1`.

## Authorized automatic scheduling preferences

Exactly five scientific scheduling preferences are implemented:

1. `VD_WITH_FAT_MEAL_PREFERENCE`
   - oral vitamin-D identity must be confirmed;
   - a legitimate meal/snack slot with known dietary-fat context is required to apply it;
   - it is a soft preference only;
   - no clock-time claim;
   - no intake block when fat context is unavailable.

2. `CALCIUM_CARBONATE_WITH_MEAL`
   - exact calcium-carbonate form is required;
   - calcium citrate and unknown calcium form do not inherit the rule;
   - output remains a meal preference, not a medical necessity.

3. `CALCIUM_IRON_AVOID_SAME_EVENT`
   - applies only to separately schedulable calcium and iron supplement items;
   - fixed combination products are never logically split;
   - `minimum_gap_minutes` remains null;
   - no universal two-hour or other numeric gap is invented.

4. `IRON25_ZINC_AVOID_SAME_EVENT`
   - trigger is confirmed supplemental elemental iron at or above 25 mg for the event;
   - display rounding is never used for classification;
   - fortified-food iron cannot trigger it;
   - compound/product mass cannot substitute for elemental iron;
   - multiple sub-threshold iron products are not silently aggregated into a trigger;
   - fixed combination products remain intact;
   - `minimum_gap_minutes` remains null.

5. `CALCIUM_SPLIT_EVENT_PREFERENCE`
   - uses the accepted <=500 mg elemental-calcium absorption evidence only as an evidence
     boundary;
   - can rearrange already-confirmed intact independently schedulable units;
   - cannot change total planned amount;
   - cannot manufacture two doses from one indivisible unit;
   - the 500 mg evidence boundary is not a personalized dose target.

The broad omega-3 ethyl-ester meal rule is intentionally not implemented. KIR-144 found that
`ethyl_ester` alone is insufficient because delivery-system technology can alter food
dependence.

## Input contract

`SchedulingItem` is an immutable planned-event snapshot.

Every amount supplied to a scheduling item must already be a canonical `ComputedAmount` on
`QuantityBasis.ABSOLUTE`. KIR-119 does not infer serving quantities, elemental conversion,
product units, or chemical form.

The caller must supply an opaque `context_revision` that changes whenever any product,
formulation, source, serving, confirmed amount, or other rule-relevant input changes. Items,
meal slots, instructions, reference queries, and user preferences must bind to the same revision.
A mixed revision is rejected before evaluation.

## Precedence

The engine follows the KIR-144 precedence contract:

1. unresolved / high-risk applicability;
2. clinician or exact product instruction;
3. governed scientific rule;
4. user routine preference;
5. arbitrary layout/defaults.

Any clinician/product instruction touching an item blocks generic automatic optimization for
that item because KIR-119 does not parse or override those instructions. Explicit instruction
conflict is surfaced as an indeterminate state rather than choosing a winner.

Medication or special-population context without a validated rule set changes the global
scheduling state to `WITHHELD_HIGH_RISK_CONTEXT`. It never becomes "no interaction".

User Morning / Day / Evening preferences are returned separately as
`UserRoutinePreference` with user-preference provenance. They are never copied into scientific
rule provenance.

## Structured result boundary

A `SchedulingRuleResult` preserves:

- ruleset version;
- rule ID and rule version;
- decision class;
- status and machine-readable reason;
- exact input context revision;
- participating item IDs;
- source snapshots;
- known and unknown facts;
- resolution path;
- non-droppable warnings.

The schema intentionally prevents strengthening:

- scientific `clock_time_preference` must remain null;
- `minimum_gap_minutes` must remain null for the authorized separation rules;
- personal safety conclusion is always withheld;
- personalized dose instruction is always disallowed;
- medical-necessity claims are always disallowed.

`NO_SUPPORTED_RULE_FOUND` always carries a warning that it is not safety or compatibility
clearance.

## Scientific provenance

The ruleset snapshots the accepted KIR-143/KIR-144 sources used by the five rules:

- NIH ODS Iron — Health Professional Fact Sheet;
- NIH ODS Zinc — Health Professional Fact Sheet;
- NIH ODS Calcium — Health Professional Fact Sheet;
- NIH ODS Vitamin D — Health Professional Fact Sheet;
- Dawson-Hughes et al., dietary-fat / vitamin-D3 absorption trial,
  DOI 10.1016/j.jand.2014.09.014, PMID 25441954.

Jurisdiction is preserved: these administration sources are biological/public-health evidence
and do not silently become EU legal reference values.

Numeric scientific parameters are data, not procedural magic numbers:

- elemental supplemental iron same-event threshold: 25 mg;
- calcium absorption evidence boundary: 500 mg.

Both retain source keys and a semantic role. The calcium value is explicitly marked
`EVIDENCE_BOUNDARY_NOT_DOSE`.

## Aggregation and duplicate-source output

KIR-119 consumes KIR-114 `DailyAggregationResult` without changing KIR-114 semantics.

Duplicate flags are surfaced as `DuplicateSourceResult` with informational status only.
They do not become a safety verdict and do not authorize discarding distinct contributions.

Partially unresolved daily aggregates are never compared as confirmed totals.

## Reference comparison output

Reference requests select an exact KIR-114 `AggregateKey` and carry a KIR-115
`ReferenceQuery` bound to the same context revision.

For a complete aggregate, KIR-119 reconstructs a provenance-preserving `PER_DAY`
`ComputedAmount` and calls the accepted KIR-115 lookup/comparison API.

For an incomplete or missing aggregate, comparison is withheld.

KIR-119 does not convert NRV / PRI / AI / UL / SAFE_LEVEL into product-unit quantities or
personalized doses. The KIR-115 personal-safety-withheld semantics remain intact.

## Stale-result invalidation

`rule_result_is_stale()` invalidates a scheduling result when:

- context revision changes;
- ruleset version changes;
- rule version changes;
- a required source disappears;
- source lifecycle is no longer active;
- source version or stable identifier changes.

Historical result snapshots preserve the exact source records used at evaluation time.

## Determinism

Evaluation order is canonicalized. Input ordering must not change output ordering or rule
classification.

Threshold arithmetic uses exact mass conversion and exact rational summation where event-level
cross-product aggregation must be examined for an explicit unresolved state.

## Explicit non-goals

KIR-119 does not implement:

- generic omega-3 ethyl-ester meal automation;
- generic calcium/iron or iron/zinc hour gaps;
- generic zinc/magnesium separation;
- forced vitamin-C + iron grouping;
- generic iron fasting automation;
- generic ferrous-sulfate intervals;
- medication-interaction guessing;
- generic Morning / Day / Evening biological placement;
- product-unit dose derivation from scientific reference values;
- LLM-generated rules.

These remain outside the authorized MVP automatic rule set.
