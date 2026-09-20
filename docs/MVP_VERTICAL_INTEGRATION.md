# KIR-122 — MVP vertical integration

KIR-122 connects the accepted MVP contracts into one Telegram-native journey without
creating a second scientific authority.

## User journey

The production manual path is:

1. create/open a Telegram user;
2. add a supplement and explicitly confirm its product-unit / label-serving facts;
3. save the user's planned product-unit quantity;
4. explicitly enter and confirm supported label composition rows;
5. derive per-unit and planned-daily amounts through KIR-113;
6. aggregate current-plan contributions through KIR-114;
7. bind the aggregate to the same immutable KIR-122 context revision used by KIR-119;
8. show deterministic scheduling rationale without converting preferences into requirements;
9. resolve reference values through KIR-115 with the exact current applicability context;
10. use Today / reminders / intake actions / History from KIR-120.

The Telegram projection is Russian-first. KIR-116 and KIR-120 state machines remain
transport-independent and unchanged; the projection translates operational copy and keeps
callback identities intact.

## Immutable context

Every vertical calculation is built from one repeatable-read PostgreSQL snapshot containing:

- current technical profile revision;
- current tracked-supplement revision;
- formulation and serving identity;
- current plan head, plan version, and planned events;
- source version/supersession state;
- confirmed amount identities;
- accepted KIR-115/KIR-119 semantic dataset versions.

A deterministic SHA-256 digest becomes the KIR-122 context revision. The KIR-114 result is
immediately wrapped in BoundDailyAggregation with that same revision before KIR-119 is
called. Why?/Sources callbacks carry a short projection of the revision and re-read current
authoritative state; if it changed, the old view fails closed instead of relabelling stale
evidence as current.

## Manual composition boundary

Manual nutrient entry stores only an explicitly reviewed fact for the currently confirmed
label-serving basis. It does not infer:

- elemental equivalence;
- chemical form;
- IU-to-mass conversion;
- a nutrient that is absent from the accepted identity set;
- a recommended or medically appropriate dose.

A duplicate manual nutrient row is rejected rather than silently overwritten. Correction or
deletion therefore needs an explicit future correction workflow instead of destructive
replacement.

## Reference and safety presentation

KIR-122 reads KIR-115 values at runtime. The Russian presentation does not duplicate numeric
UL, SAFE_LEVEL, or other scientific constants.

The UI preserves these distinctions:

- unknown applicability is not replaced by an adult default;
- SAFE_LEVEL is not presented as an UL;
- no-UL states are not presented as unlimited safety;
- below/equal/above is only a deterministic comparison, not a personalized safety verdict;
- no supported KIR-119 rule is not compatibility clearance;
- evidence-backed preferences remain preferences;
- KIR-119 null minimum gaps remain null;
- Morning / Day / Evening remain user routine labels, not biological timing claims.

## Photo path and production gate

KIR-117 deliberately does not select a production OCR/VLM provider. KIR-122 therefore does
not invent one.

This integration supplies an idempotent durable ConfirmedLabelSink boundary. A successfully
confirmed KIR-117 record persists:

- the accepted structured KIR-111 extraction;
- project-owned candidate / idempotency identity;
- image content SHA-256;
- provider/model/adapter/prompt/schema/preprocessing revisions;
- request/completion/confirmation timestamps;
- optional raw-provider-response SHA-256.

Source pixels are not persisted by this sink. The KIR-117 pipeline deletes the transient
image only after durable persistence succeeds.

The production bot intentionally continues to hide the photo action until all KIR-117
operational prerequisites are explicitly authorized and wired:

1. a storage-native transient store with automatic expiry of no more than 30 minutes;
2. an authorized provider/configuration satisfying privacy and region gates;
3. the frozen provider benchmark corpus required by Project Control;
4. a durable restart-safe candidate review session;
5. a Telegram confirmation/edit surface that shows the full field scope and source evidence
   while the source still exists.

InMemoryTransientImageStore is used only by tests and is never created by main().

Until those gates are satisfied, manual entry is the user-visible fallback. The UI says that
photo/barcode paths are hidden rather than pretending they are available.

## Operational state separation

KIR-122 does not collapse:

- recurring plan template;
- generated Today occurrence;
- reminder delivery attempt;
- user intake action;
- correction / entered-in-error history state.

Notification delivery is never treated as proof of intake. Today remains the operational
home, Plan remains the recurring-template editor, and History remains the audit/correction
view.

## Privacy

No raw Telegram bodies, label pixels, provider raw responses, medication text, or complete
profile payload are added to logs by this integration. The durable photo sink stores only
confirmed structured evidence and bounded provenance described above.

## Verification

Release evidence for KIR-122 must include, on the exact reviewed PR head:

- mandatory Linux Ruff / format / Mypy / PostgreSQL Pytest lane;
- KIR-121 independent ENG4 safety regression lane;
- clean-account vertical integration regression;
- duplicate callback / durable sink idempotency checks;
- stale context / Why?/Sources invalidation;
- Russian-first operational projection checks.

Windows remains the pre-existing non-blocking compatibility lane under the accepted
least-privilege setup-python limitation; it is not a substitute for the mandatory Linux
release lane.
