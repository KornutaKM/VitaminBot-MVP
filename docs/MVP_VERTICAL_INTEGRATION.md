# KIR-122 MVP vertical integration

## User journey

KIR-122 connects the accepted MVP components into one Telegram-native path:

1. create or open the user profile;
2. add a supplement through manual entry, or enter the explicit photo fallback when no
   authorized production recognition provider is configured;
3. confirm product-unit and serving facts;
4. confirm label nutrient rows explicitly;
5. define the user's recurring product-unit plan;
6. derive per-unit and per-day nutrient amounts through KIR-113;
7. aggregate confirmed planned contributions through KIR-114;
8. evaluate KIR-119 scheduling rules against the same immutable snapshot;
9. show totals/contributors and KIR-146 provenance/reference cards;
10. use KIR-120 Today, reminders, and History for occurrences created from the confirmed plan.

No database hand editing is part of the user journey.

## One-snapshot safety boundary

KIR-122 reads the inputs for totals and rules in one PostgreSQL
`REPEATABLE READ READ ONLY` transaction. The snapshot includes:

- current tracked supplement/formulation and serving identity;
- current intake-plan head and events;
- confirmed product amounts;
- source identity/version/retrieval metadata;
- presentation-profile revision.

A canonical SHA-256 digest becomes `context_revision`. KIR-114 aggregation and KIR-119
rule evaluation are bound to that same revision. Computed scientific results are not persisted
as a new authority. Editing a plan or source-backed amount therefore produces a new revision
and a fresh computation rather than relabelling stale output as current.

## Confirmed label amount boundary

Manual composition entry records only an explicit user-confirmed label statement. The supported
MVP path asks separately for:

- governed canonical substance identity from a bounded allowlist;
- numeric value;
- literal unit;
- final confirmation.

An unknown substance, unsupported identity, stale callback, missing amount, conflicting input,
or normalization failure is not converted to zero and is not guessed.

The manual path intentionally omits folate/folic-acid and omega-3/EPA/DHA shortcuts because
their amount semantics can require additional evidence. They must not be silently collapsed
into an analyte identity.

## Scheduling rules

KIR-122 does not introduce scientific rule constants. It supplies KIR-119 with confirmed
event snapshots and shows only the governed result.

In particular:

- a user Morning/Day/Evening choice remains a user routine preference;
- a meal rule remains a preference, not medical necessity;
- a separation rule does not invent a numeric time gap when KIR-119 has none;
- a split preference can only redistribute already planned intact discrete units;
- `NO_SUPPORTED_RULE_FOUND` is not safety or compatibility clearance;
- insufficient evidence stays visible as insufficient evidence.

## Reference and nutrient-card boundary

KIR-146 remains the governed educational/reference presentation surface. KIR-122 may attach a
complete confirmed daily aggregate and its `context_revision`, but it does not invent
population applicability. If age/sex/life-stage or another required context is unavailable,
the KIR-115/KIR-146 path must remain unable to make a personalized comparison.

The current accepted scientific card content is English. KIR-122 provides Russian-first shell,
workflow, totals, rationale, reminder, and safety-state copy, but deliberately does not
machine-translate governed KIR-146 scientific claims into a second unreviewed authority.

## Photo recognition limitation

KIR-117 defines the safe photo-recognition contract, but its accepted scope explicitly does not
select a production OCR/VLM provider. A production photo path additionally requires an
authorized provider configuration and production transient image storage with lifecycle/TTL
enforcement.

Until those gates are satisfied, the Telegram photo option fails closed to a clear manual-entry
fallback. It does not fabricate extraction results, confidence, or confirmation, and it stores
no inferred label facts.

## Idempotency and stale actions

Telegram delivery can repeat. Nutrient-entry mutations use the existing durable
`bot_action_receipts` identity, while confirmation is additionally bound to the current
supplement/session revision. Exact replay returns the existing result; a stale revision cannot
silently overwrite newer state.

## Destructive lifecycle

KIR-122 label amounts belong to the existing product formulation. The canonical schema already
uses `ON DELETE CASCADE` from `product_formulations` to `product_amounts`; KIR-122 adds a
database integration regression proving that a manual supplement with confirmed composition
can still be removed atomically with its formulation/source support rows.

## Release verification

Release evidence must be taken from the exact PR head:

- Linux lint/format/type/tests;
- the independent KIR-121 safety regression job;
- applicable Windows compatibility evidence when the runner is available;
- PR diff/scope review;
- Project Control independent acceptance.

Passing a development smoke test or one earlier commit is not release evidence.
