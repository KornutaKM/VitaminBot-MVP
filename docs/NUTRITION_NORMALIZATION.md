# KIR-113 Deterministic Nutrition Normalization

## Scope

This module performs deterministic unit and serving normalization on top of the accepted KIR-109 domain contract. It contains no recommendation algorithm, reference value, UL, SAFE_LEVEL, diagnosis rule, or LLM arithmetic.

## Generic unit conversion

Generic conversion is restricted to compatible MVP mass units:

- g
- mg
- ug

It is exact and uses rational arithmetic internally. Activity, count, and volume units cannot enter the generic mass converter.

There is intentionally no universal IU conversion.

## Scientific conversion rules

Cross-dimension conversion requires an explicit immutable `ScientificConversionRule`.

A rule contains exactly one positive rational factor expressing `to_unit per from_unit`. Reverse conversion is derived from its exact reciprocal. There is no independently stored reverse factor.

This single-source-of-truth invariant prevents forward/reverse scientific constants from diverging.

Every rule is scoped by:

- analyte;
- exact unit pair;
- allowed chemical forms;
- equivalence basis;
- rule ID/version;
- authority source ID;
- source version;
- source locator.

A rule is never selected by unit pair alone.

Scientific conversion returns `AmountBasis.EQUIVALENT` with the exact rule equivalence basis. It can accept either a source `AmountRecord` or a prior `ComputedAmount`, so scientific and serving normalization can compose without losing lineage.

## Vitamin D

KIR-113 implements only the accepted D2/D3 VDE equivalence from EFSA NDA 2023, DOI `10.2903/j.efsa.2023.8145`:

- stored factor: IU -> ug VDE = 1 / 40;
- reverse ug -> IU is the exact reciprocal 40 / 1;
- allowed forms: ergocalciferol (D2) and cholecalciferol (D3).

Unknown vitamin-D form fails closed.

Calcidiol monohydrate is not generalized into this MVP rule because its equivalence has separate form/applicability semantics. It remains unresolved until a separately reviewed contract authorizes it.

The D2/D3 factor must not be reused for other substances with IU/activity units.

## Serving normalization

A source amount can be normalized to a consumption unit only when:

- the amount is deterministically usable;
- amount quantity basis matches the source serving basis;
- source quantity-basis lineage contains the serving basis ID;
- serving quantity/unit are explicit;
- the serving is count-based;
- consumption-unit identity is explicit.

`source_quantity_basis_ids` preserves the source basis lineage separately from `consumption_unit_id`. The latter is attached only after an explicit serving relationship is resolved; these identifiers are never overloaded as the same concept.

Scaling never changes analyte/ingredient identity or amount basis.

Therefore:

- elemental magnesium remains elemental magnesium;
- magnesium-citrate compound mass remains compound mass;
- fish-oil material remains fish-oil material;
- EPA and DHA remain separate analytes.

## Planned daily normalization

Daily planned amount is computed only from explicit `IntakePlan` events.

It never creates or implies a consumed event.

The plan must use the same consumption-unit identity as the normalized per-unit amount. A mismatch yields an unresolved result rather than silently dropping or converting an event.

Manufacturer recommended daily portion is not substituted for the user's plan.

## Arithmetic and rounding

All public quantities use `Decimal`.

Division is represented internally as an exact `Fraction`.

Finite Decimal reconstruction handles reduced denominators of the form `2^a * 5^b` exactly, including unequal powers such as `1/8 = 0.125` and `1/40 = 0.025`.

Default policy: **no rounding**.

If a result does not have a finite exact Decimal representation, computation fails with `RoundingRequiredError` unless the caller supplies an explicit `RoundingPolicy`.

A rounding policy contains:

- positive finite Decimal quantum;
- named rounding mode.

Supported MVP modes:

- half-even;
- half-up.

Rounded results retain the unrounded exact numerator/denominator plus quantum and mode in the computation trace.

The implementation does not depend on ambient Decimal context precision or rounding mode.

Non-finite source quantities are rejected before rational arithmetic. Public computed amounts also re-validate KIR-109 subject-kind/amount-basis consistency.

Presentation rounding is outside KIR-113.

## Fail-closed boundaries

The engine never:

- infers compound -> elemental mass;
- infers EPA/DHA from fish-oil mass;
- guesses vitamin-D chemical form;
- performs generic IU -> mass conversion;
- guesses a serving size;
- substitutes a label daily portion for a user plan;
- turns planned intake into consumed intake;
- invents a rounding precision;
- invokes an LLM for arithmetic or scientific constants.

Unknown/ambiguous governed inputs remain unresolved rather than becoming zero or a numeric guess.