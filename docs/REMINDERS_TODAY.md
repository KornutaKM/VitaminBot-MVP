# KIR-120 — Plan, Today, reminders, and intake actions

## State model

KIR-120 preserves four separate durable concepts:

1. **Recurring template** — the current versioned `intake_plans` /
   `planned_intake_events` definition.
2. **Generated occurrence** — one local-day snapshot in `reminder_occurrences`.
3. **Notification/delivery attempt** — transport state in
   `reminder_delivery_attempts`.
4. **User intake action/correction** — append-only `occurrence_actions`, with a
   real `intake_events` row created only for explicit **Taken**.

A sent Telegram reminder never changes occurrence state to Taken.

## Plan semantics

Morning / Day / Evening are user routine buckets only. Their default local clock
times are configurable with:

- `REMINDER_MORNING_TIME`;
- `REMINDER_DAY_TIME`;
- `REMINDER_EVENING_TIME`.

They are product scheduling defaults, not biological timing claims.

Users may instead choose an explicit local `HH:MM` time. Schedule edits create a
new plan version while copying the already-confirmed product-unit quantity and
unit identity unchanged.

An occurrence is a snapshot of the plan version that generated it. Editing the
recurring Plan later does not rewrite an already-generated Today occurrence.
For the MVP, one occurrence per tracked supplement per local day is supported.

## Timezones and DST

Occurrence generation requires an explicit user IANA timezone. There is no hidden
timezone fallback.

Local times are resolved through `zoneinfo`. If a local clock time is ambiguous
or nonexistent at a DST transition, materialization fails closed. VitaminBot does
not silently choose a fold or shift the user's explicit time.

## Reminder execution

The worker persists a delivery claim before any Telegram send. Claims are validated
once for grouping and then **every delivery is revalidated again immediately before
its group's actual Telegram send**. Cancelled, expired, stale, or non-pending claims
are removed from that final group; an empty group is not sent.

- duplicate execution keys cannot create a second claim;
- successful delivery is transport state only;
- explicit send failures may be retried, with a maximum of three failed attempts
  per occurrence revision;
- **Later** is a one-off occurrence reschedule and is limited to one use;
- Taken / Skip / correction cancels outstanding claimed deliveries;
- an expired `claimed` delivery is marked `uncertain` and is **not**
  automatically resent.

The `uncertain` rule is deliberate. Telegram does not provide a transactional
send primitive that can be atomically committed with PostgreSQL. If the process
crashes after Telegram accepted a message but before the database recorded
`sent`, automatically retrying could duplicate the reminder. KIR-120 therefore
fails closed on that crash gap.

The runner may batch same-minute due items for one Telegram user into one message,
but every occurrence retains its own Taken / Later / Skip / Why? actions. There is
no Taken-all action.

## Intake actions and correction

**Taken** creates an `intake_events` row from the occurrence snapshot. The
confirmed plan quantity is never modified by reminder scheduling or by Later.

**Skip** records an action but creates no intake event.

**Later** changes only the occurrence `due_at`; the recurring template is not
mutated.

Correction marks the prior Taken/Skip action entered in error. If the corrected
action was Taken, the linked intake event is also marked `entered_in_error_at`.
The occurrence moves to `needs_review` and is not automatically reminded until
the user explicitly records the current state.

## Scientific boundary

KIR-120 does not implement KIR-119 scientific scheduling rules. If no governed
planning note is attached, `Why?` states that the timing is the user's routine
preference. No compatibility, separation, meal-context, dose, safety, or
biological Morning/Day/Evening claim is inferred.

## Bot-native surfaces

- `/plan` — recurring-template view;
- `/today` — local-day occurrence view;
- `/history` — action/correction audit view.

Reminder messages and Today callbacks are revision-aware. Stale callbacks fail
closed and cannot create duplicate intake events.
