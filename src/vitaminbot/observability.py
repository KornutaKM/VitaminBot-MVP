from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal, Protocol

MetricName = Literal[
    "reminders_due",
    "reminders_sent",
    "reminders_failed",
    "reminder_lag_seconds",
    "stale_callback_count",
    "db_transaction_errors",
    "photo_extraction_started",
    "photo_extraction_confirmed",
    "photo_extraction_rejected",
    "corrections_recorded",
]


class MetricsSink(Protocol):
    """Small privacy-safe metrics boundary.

    Callers may emit only an approved metric name and a numeric value. User ids,
    supplement names, callback payloads, free text, and health data are deliberately
    absent from the interface.
    """

    def increment(self, name: MetricName, value: int = 1) -> None: ...

    def observe(self, name: MetricName, value: float) -> None: ...


class NullMetricsSink:
    def increment(self, name: MetricName, value: int = 1) -> None:
        del name, value

    def observe(self, name: MetricName, value: float) -> None:
        del name, value


@dataclass(slots=True)
class LoggingMetricsSink:
    logger: logging.Logger

    def increment(self, name: MetricName, value: int = 1) -> None:
        self._emit("counter", name, float(value))

    def observe(self, name: MetricName, value: float) -> None:
        self._emit("gauge", name, value)

    def _emit(self, kind: str, name: MetricName, value: float) -> None:
        payload = {
            "kind": kind,
            "metric": name,
            "value": value,
        }
        self.logger.info("vitaminbot_metric %s", json.dumps(payload, separators=(",", ":")))


NULL_METRICS = NullMetricsSink()
