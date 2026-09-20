# KIR-109 Nutrition Domain Contract

## Purpose

This document defines the canonical VitaminBot nutrition-domain boundary. It implements the accepted KIR-124 glossary/source invariants without introducing recommendations, dose targets, UL/reference constants, interaction thresholds, or scientific conversion constants.

Schema version: `1.0.0`.

## Identity boundaries

The model keeps these identities separate:

1. **Tracked analyte** — aggregation target such as magnesium, vitamin D, EPA, or DHA.
2. **Ingredient** — declared formulation material such as fish oil or magnesium citrate.
3. **Chemical form** — chemically specific identity where resolved.
4. **Product identity** — commercial product identity. Market jurisdiction has an explicit resolution status; an unknown/ambiguous market is represented without a fabricated jurisdiction code.
5. **Product formulation version** — versioned formulation/source bundle for a product.
6. **Tracked supplement instance** — the user's specific tracked container/item.
7. **Intake plan** — user/application plan referencing a tracked instance.
8. **Consumed intake event** — explicit confirmed consumption; never inferred from elapsed schedule time.

Canonical analyte identity does not imply an EU regulatory classification. Regulatory classification is a separate source-scoped record.

## Quantity contract

Every resolved nutrient/ingredient amount carries:

- subject kind and subject ID;
- exact numeric value represented with `Decimal`;
- unit;
- amount basis;
- quantity basis;
- product/source provenance;
- evidence status;
- resolution status.

Unknown or ambiguous values may retain partial/raw evidence but are not deterministically usable.

`None` means absent/unresolved. Zero is a real numeric value and must never be used as an unknown sentinel.

### Amount-basis invariants

- `INGREDIENT_COMPOUND` / `MATERIAL` reference ingredient subjects.
- `ANALYTE` / `ELEMENTAL` / `EQUIVALENT` reference analyte subjects.
- magnesium-citrate compound mass is not elemental magnesium mass;
- fish-oil material mass is not EPA, DHA, or total omega-3;
- equivalent amounts require an explicit equivalence basis;
- derived values require versioned derivation provenance and input lineage.

## Unit boundary

The KIR-109 domain contract records dimensions but does not implement KIR-113 conversion logic.

Generic canonical internal units:

- mass → micrograms (`ug`);
- volume → millilitres (`mL`);
- count → `count`;
- activity/equivalence → **no generic canonical unit**.

Metric mass/volume conversion is a future deterministic conversion concern.

`IU` is represented as an activity unit. KIR-109 deliberately provides no universal `IU → ug` operation. Any such conversion must be analyte/form/basis-specific, versioned, authoritative, and implemented under an approved conversion rule.

Compound→elemental stoichiometry is not implemented. If a label only supplies compound mass, elemental intake remains unresolved unless a later approved exact-form conversion registry exists.

## Serving and intake boundaries

The following label bases remain distinct:

- per consumption unit;
- per label portion;
- per manufacturer-recommended daily portion;
- per 100 g;
- per 100 mL;
- another explicit basis.

A capsule/tablet/dropper unit is not automatically a serving.
A serving is not automatically the manufacturer's recommended daily portion.
The user's plan is not the manufacturer's recommendation.
A plan is not proof of consumption.

Derived per-unit normalization may only be added later when the source basis and unit relationship are explicit and provenance is retained.

## Provenance

`SourceRecord` is first-class and immutable. It can represent:

- EU law;
- EFSA opinion;
- official guidance;
- product label;
- authoritative secondary reference;
- chemical ontology;
- user declaration.

It preserves stable identifier, version, retrieval date, optional adoption/publication/effective dates, jurisdiction, locator, and supersession links.

A deterministic derived amount additionally preserves:

- rule ID;
- rule version;
- authority source ID;
- every input amount ID.

Historical results must remain reproducible against the versions used when the result was produced.

## Population applicability

Population applicability is source-native. The contract supports only dimensions required by governed source matching:

- source label;
- age boundaries and inclusivity;
- sex applicability where the source actually distinguishes it;
- life stage where the source actually distinguishes it;
- optional source-native physiological condition;
- explicit extra source conditions.

There is no implicit adult fallback. Missing required applicability must be handled as unresolved by downstream reference matching.

This structure is source metadata, not permission to pre-collect a sensitive user profile.

## Candidate/confirmation separation

Recognition or catalog candidates are not canonical truth.

`CandidateResolution` preserves all candidates and separately records:

- candidate state;
- user confirmation state;
- scientific-resolution state;
- selected candidate, only if explicitly confirmed.

A selected candidate is valid only when confirmation state is `CONFIRMED`, and the selected retained candidate must still be `ACTIVE`. Unconfirmed or rejected resolutions cannot carry a selected candidate. An excluded candidate cannot be promoted to canonical truth.

Selecting one candidate does not destructively merge or delete the alternatives. This supports correction, auditability, and stale-result invalidation.

## Fail-closed invariants

Downstream code must withhold deterministic numeric use when required identity, unit, basis, source, or applicability is unresolved.

Never:

- infer elemental amount from compound mass;
- infer EPA/DHA from fish-oil mass;
- treat IU as a generic mass unit;
- coerce unknown to zero;
- collapse label portion, consumption unit, and daily portion;
- turn a plan into a consumed event;
- silently substitute adult/nonpregnant/default population;
- fabricate a product market jurisdiction when it is unknown or ambiguous;
- select a product/formulation candidate before explicit confirmation;
- promote an excluded candidate to canonical truth;
- silently merge duplicate product candidates;
- erase source/version lineage;
- originate a scientific constant from LLM prose.

## Downstream ownership

- KIR-113 owns deterministic conversion and serving normalization.
- KIR-115 owns versioned EU/EFSA reference-value records and comparison semantics.
- ENG3 recognition work may produce candidates/evidence but cannot silently establish canonical truth.
- ENG1 persistence maps these contracts into durable storage without changing their semantics.
- ENG4 independently validates fail-closed and adversarial behavior.

KIR-109 itself contains no recommendation algorithm.
