# KIR-116 Telegram onboarding and manual supplement entry

## Scope

This slice implements the first usable bot-native VitaminBot flow without vision:

- `/start` information/onboarding;
- manual supplement capture and explicit confirmation;
- product-unit serving entry;
- optional Morning / Day / Evening user plan;
- supplement list/detail;
- profile review/correction for technical timezone and locale;
- edit/remove for supplements created by this manual flow.

Photo and barcode controls are intentionally absent until those acquisition paths are shipped.

## Architecture boundaries

Telegram is a transport adapter only. `KIR116Controller` owns transport-independent use-case state and returns plain `Screen` projections. `KIR116Store` owns PostgreSQL transactions and durability.

Telegram callback payloads contain only compact actions, opaque references, and revisions. They do not contain supplement names, quantities, profile values, or other sensitive payloads.

Bot message text is a projection. State is persisted before the adapter edits or sends a Telegram message.

## Durable state, retries, and stale actions

Pending manual input and edit flows are stored in PostgreSQL rather than process memory. A process restart therefore does not silently lose the authoritative pending state.

Every state-changing Telegram update carries a server-side action key. `bot_action_receipts` makes duplicate delivery idempotent within the user scope.

`bot_sessions` keeps a monotonically increasing revision even after a flow is cancelled or completed. The row moves to `idle` rather than being deleted. This prevents an old callback revision from becoming valid again after a later flow recreates similar state.

Stale callbacks fail closed and return the current navigation surface instead of replaying an obsolete mutation.

## Product facts and plan semantics

Manual confirmation means only that the structured record matches what the user entered. It does not assert that the supplement is safe, appropriate, complete, or scientifically resolved.

The manual product name is stored on the user-owned tracked supplement record. Canonical support rows created by this slice use opaque identifiers and generic text, so the user-entered supplement name is not copied into shared canonical product metadata.

A plan stores a positive quantity in the selected product consumption unit plus a routine bucket: Morning, Day, or Evening. Those buckets are user routine labels, not claims of biological timing superiority.

KIR-116 does not implement nutrient conversion, IU conversion, compound-to-elemental conversion, or serving normalization. Those semantics belong to ENG2 KIR-113 and later governed integration.

## Profile and privacy

Generic onboarding does not request medication, condition, pregnancy, age/life-stage, or other speculative medical/applicability data.

The implemented profile surface contains only timezone and locale. Both values are reviewable and correctable. Future governed safety/applicability fields must be requested just in time with an explicit purpose.

The `/start` screen is an information/onboarding surface. It does not claim to establish a GDPR legal basis or Article 9 consent decision; those production compliance questions remain explicitly unresolved under KIR-137.

No application log or analytics event in this slice records raw supplement/profile payloads.

## Removal semantics

Removal is restricted in this slice to supplements created by the manual KIR-116 flow.

The removal transaction deletes:

- the user-owned tracked supplement;
- the current and historical saved plans that cascade from that tracked instance;
- linked intake history that cascades from that tracked instance;
- the manual formulation/product/source support rows created only for that manual record.

It does not merge, alter, or delete another tracked supplement.

## Running

Run migrations explicitly before starting the bot:

    vitaminbot-migrate

Then configure `DATABASE_URL` and `TELEGRAM_BOT_TOKEN` through deployment/local secrets and run:

    vitaminbot-bot

Bot startup does not mutate the schema implicitly.

## Verification focus

Repository integration tests run against real PostgreSQL and cover:

- first manual capture through explicit confirmation;
- invalid and valid quantities;
- duplicate message/callback delivery;
- plan creation and duplicate callback safety;
- profile correction;
- supplement edit;
- stale object callbacks;
- process/controller restart with pending state;
- callback payload size/privacy;
- cancel/restart stale-callback ABA protection;
- exact removal cleanup.


## Serving correction integrity

Serving corrections are versioned. The current tracked supplement points to the latest manual
consumption-unit/serving pair, while previously saved plan and intake records keep their original
consumption-unit identity. Editing a serving therefore cannot silently turn a saved “capsule” plan
into a “tablet” plan. If the current product unit differs from the saved plan unit, the bot surfaces
that mismatch and asks the user to review the plan explicitly.

This KIR-116 slice accepts count-based product units only: capsule, tablet, softgel, scoop, and drop.
Volume entry such as mL is intentionally hidden and rejected at the persistence boundary until a
governed volume-aware path is implemented. Volume is never coerced to `basis_unit='count'`.
