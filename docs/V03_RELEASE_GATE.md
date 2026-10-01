# VitaminBot v0.3 release gate

This checklist is the release contract for the Telegram-first v0.3 loop. It is intentionally
operational: every item must be backed by deterministic application or persistence behavior and
an automated regression test.

## Golden journeys

| Journey | Required invariant | Regression coverage |
| --- | --- | --- |
| New user | Start -> quick add -> plan -> Today without requiring composition data | `tests/test_v03_quick_add_renderer.py`, `tests/test_v03_today_renderer.py` |
| Daily loop | Today -> Later -> reminder -> Taken; delivery is not intake proof | `tests/test_kir120_integration.py` |
| Restart safety | Restarted worker cannot duplicate a claimed reminder or intake event | `tests/test_kir120_integration.py` |
| DST safety | Ambiguous and nonexistent local times fail closed | `tests/test_kir120_integration.py` |
| Supplement lifecycle | Pause cancels pending reminders; resume starts from the next valid schedule | `tests/test_kir120_integration.py`, `tests/test_v03_supplement_detail.py` |
| Inventory | Manual balance is nonnegative; Taken/correction ledger is deterministic | `tests/test_v03_inventory.py`, `tests/test_kir120_integration.py` |
| Adherence | 7/30-day summaries report planned/taken/skipped/unresolved without health judgment | `tests/test_v03_adherence.py` |
| Stale actions | Revision-bound callbacks fail closed and do not write duplicate intake | `tests/test_kir120_integration.py`, `tests/test_v03_today_renderer.py` |
| Account control | Export is versioned; deletion is explicit, nonce-bound, cascading, and old tokens cannot delete recreated accounts | `tests/test_v03_account_data.py` |
| Safety regression | Numeric safety behavior remains deterministic and independent from LLM output | `tests/test_safety_regression_kir121.py` |

## Observability contract

Runtime metrics are privacy-safe by construction. The metrics interface accepts only an approved
metric name and a numeric value. It must never receive Telegram ids, callback payloads, supplement
names, image bytes, medication text, profile values, or other free text.

v0.3 emits:

- `reminders_due`
- `reminders_sent`
- `reminders_failed`
- `reminder_lag_seconds`
- `stale_callback_count`
- `db_transaction_errors`

The photo-extraction and correction metric names are reserved in the type contract but should only
be emitted when those production paths are instrumented.

## Release procedure

1. Migrations apply cleanly to a fresh PostgreSQL database and are idempotent.
2. Linux quality, full pytest, safety regression, Windows compatibility, and the explicit v0.3
   release-journey step are green.
3. Run bot and worker as separate processes.
4. Verify one real Telegram reminder can be delivered and explicitly marked Taken.
5. Verify export before destructive account deletion.
6. Do not release with unresolved DST, stale-callback, duplicate-delivery, or migration failures.
