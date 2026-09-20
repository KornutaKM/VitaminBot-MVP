# KIR-146 — Telegram nutrient information cards

KIR-146 is a presentation/application layer over accepted scientific contracts. It does not
author scientific claims, reference values, safety thresholds, personalized doses, or timing
rules.

## Governing inputs

- KIR-145 supplies immutable approved educational claim copy and claim provenance.
- KIR-115 is the only runtime numeric authority for reference and safety values.
- KIR-154 controls card rendering, fail-closed behavior, localization, provenance, and the
  RB-CARD-1..24 release blockers.
- KIR-153 controls DHA-specific UL / SAFE_LEVEL separation and source-native applicability.
- KIR-144 controls administration/timing wording already accepted for this slice.
- KIR-129 controls fail-closed status/envelope semantics.

Dynamic KIR-119 output is deliberately not consumed by this slice until KIR-119 is accepted.

## Data separation

The card-content module contains immutable, versioned KIR-145 claim records. Scientific
daily reference/safety measurement patterns are rejected in static claim text so
localized/presentation copy cannot become an independent numeric authority. Accepted
non-reference illustrative label examples remain verbatim KIR-145 copy.

The KIR-146 application renderer resolves the current KIR-115 dataset at render time. A rendered
binding captures:

- content ID and content version;
- dataset version;
- immutable context revision;
- exact KIR-115 record ID and reference type;
- source key, exact source URL and source version;
- applicability state/reasons and candidate record IDs;
- comparison state when a confirmed normalized per-day amount is available.

Current output is invalid when its content/source/dataset/context binding is stale. Historical
rendering uses the captured binding and reference display snapshots; it never reconstructs old
scientific state from newer copy or a newer reference record.

## Fail-closed behavior

A card does not assume an adult, nonpregnant, jurisdiction, form, exposure basis, dietary
phytate condition, elemental amount, EPA/DHA amount, or medication result when the required
input is absent.

Unsupported locale/jurisdiction, missing governed content, unresolved applicability, ambiguous
reference selection, partial coverage, or superseded source state cannot produce a substitute
numeric reference.

A CANNOT_ASSESS envelope retains the unknown/ambiguous facts, withheld conclusion, provenance,
resolution path, escalation path where applicable, comparison context, and non-droppable
warnings.

## Numeric rendering

Every reference/safety numeric token is formatted directly from the matched KIR-115
ReferenceRecord. The renderer does not maintain numeric copies and does not independently round
or convert reference values.

Reference types stay typed: NRV, AR, PRI, AI, RI, UL, SAFE_LEVEL. A UL is never presented as a
target or dose. SAFE_LEVEL stays distinct from UL, target, dose, personal maximum, or personal
safety clearance. A nonnumeric/no-UL state keeps its governed reason and never becomes an
unlimited-safety statement.

Confirmed amounts are compared only through the KIR-115 comparison API; presentation code does
not implement a second comparison algorithm.

## DHA scope

The DHA card can show the current DHA-specific safety record only when KIR-115 itself matches
the source-native exposure. Applicability metadata (exposure basis, allowed source/form
constraints, EPA/DHA ratio condition, and background-diet exclusion where present) is generated
from that matched record.

Generic fish oil, generic omega-3, or generic EPA+DHA cards do not inherit a DHA-specific
SAFE_LEVEL. Below a matched SAFE_LEVEL is not personal safety clearance; above it is not an
unsafe/toxic classification from that reference alone.

## Telegram UX

The acceptance baseline is a regular bot message:

- /nutrient lists approved cards;
- /nutrient <name> opens a card;
- Reference values shows typed record bindings;
- Why / Sources shows exact claim and reference provenance;
- Back returns to the card/list.

No Mini App is required. Callback payloads carry only compact card keys, never raw scientific
copy or source URLs.

When a message must be shortened, optional food context is removed before secondary function
or identity context. Safety/applicability qualifiers, withheld conclusions, administration
limits, important limitations, and provenance access are never silently dropped; if they cannot
fit, rendering fails rather than weakening the scientific/safety meaning.

## Localization

Only approved content versions/locales may render. KIR-146 does not machine-translate scientific
copy. If a requested locale has no approved version, the card fails closed rather than letting
a translator or LLM strengthen, round, invent, or remove a material qualifier.

## Verification

tests/test_kir146_cards.py maps the mandatory KIR-154 adversarial cases and also covers:

- missing/superseded source/content;
- unsupported jurisdiction and missing applicability;
- context-revision invalidation;
- exact record/source/version/locator provenance;
- historical reproducibility;
- Telegram-native command/callback behavior.

Green CI is necessary but does not override a confirmed RB-CARD blocker.
