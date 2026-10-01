from __future__ import annotations

import json
import logging

from vitaminbot.observability import LoggingMetricsSink, NULL_METRICS


def test_logging_metrics_are_numeric_and_do_not_accept_context_fields(
    caplog: object,
) -> None:
    logger = logging.getLogger("vitaminbot.tests.metrics")
    sink = LoggingMetricsSink(logger)

    logger.setLevel(logging.INFO)
    handler = logging.Handler()

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    capture = _Capture()
    logger.addHandler(capture)
    try:
        sink.increment("reminders_due", 3)
        sink.observe("reminder_lag_seconds", 12.5)
    finally:
        logger.removeHandler(capture)

    assert len(records) == 2
    payloads = []
    for record in records:
        message = record.getMessage()
        assert message.startswith("vitaminbot_metric ")
        payload = json.loads(message.removeprefix("vitaminbot_metric "))
        assert set(payload) == {"kind", "metric", "value"}
        payloads.append(payload)

    assert payloads[0] == {
        "kind": "counter",
        "metric": "reminders_due",
        "value": 3.0,
    }
    assert payloads[1] == {
        "kind": "gauge",
        "metric": "reminder_lag_seconds",
        "value": 12.5,
    }


def test_null_metrics_sink_is_safe_default() -> None:
    NULL_METRICS.increment("reminders_failed", 2)
    NULL_METRICS.observe("reminder_lag_seconds", 0.0)
