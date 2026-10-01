from __future__ import annotations

from types import TracebackType
from typing import Any, Self

import psycopg
from psycopg import IsolationLevel, sql
from psycopg.rows import dict_row

from vitaminbot.persistence.kir116 import KIR116Store
from vitaminbot.persistence.kir120 import KIR120Store, RoutineTimes
from vitaminbot.persistence.kir122 import KIR122Store
from vitaminbot.persistence.kir174 import KIR174Store


class PostgresUnitOfWork:
    """Shared transaction boundary for operational VitaminBot repositories.

    The unit of work is rollback-by-default. Call commit() explicitly after all
    cross-repository invariants have been satisfied. Nutrition shares the same
    REPEATABLE READ transaction so snapshot semantics are not weakened.
    """

    def __init__(
        self,
        database_url: str,
        *,
        schema: str = "public",
        routine_times: RoutineTimes | None = None,
    ) -> None:
        self._database_url = database_url
        self._schema = schema
        self._routine_times = routine_times
        self._connection: psycopg.Connection[dict[str, Any]] | None = None
        self._supplements: KIR116Store | None = None
        self._intake: KIR120Store | None = None
        self._nutrition: KIR122Store | None = None
        self._applicability: KIR174Store | None = None
        self._committed = False

    def __enter__(self) -> Self:
        if self._connection is not None:
            raise RuntimeError("unit of work is already active")

        connection: psycopg.Connection[dict[str, Any]] = psycopg.connect(
            self._database_url,
            row_factory=dict_row,
        )
        connection.isolation_level = IsolationLevel.REPEATABLE_READ
        connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(self._schema)))

        self._connection = connection
        self._committed = False
        self._supplements = KIR116Store(
            self._database_url,
            schema=self._schema,
            connection=connection,
        )
        self._intake = KIR120Store(
            self._database_url,
            schema=self._schema,
            routine_times=self._routine_times,
            connection=connection,
        )
        self._nutrition = KIR122Store(
            self._database_url,
            schema=self._schema,
            connection=connection,
        )
        self._applicability = KIR174Store(
            self._database_url,
            schema=self._schema,
            connection=connection,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc, traceback
        connection = self._connection
        if connection is None:
            return

        try:
            if exc_type is not None or not self._committed:
                connection.rollback()
        finally:
            connection.close()
            self._connection = None
            self._supplements = None
            self._intake = None
            self._nutrition = None
            self._applicability = None
            self._committed = False

    @property
    def supplements(self) -> KIR116Store:
        if self._supplements is None:
            raise RuntimeError("unit of work is not active")
        return self._supplements

    @property
    def intake(self) -> KIR120Store:
        if self._intake is None:
            raise RuntimeError("unit of work is not active")
        return self._intake

    @property
    def nutrition(self) -> KIR122Store:
        if self._nutrition is None:
            raise RuntimeError("unit of work is not active")
        return self._nutrition

    @property
    def applicability(self) -> KIR174Store:
        if self._applicability is None:
            raise RuntimeError("unit of work is not active")
        return self._applicability

    def commit(self) -> None:
        connection = self._connection
        if connection is None:
            raise RuntimeError("unit of work is not active")
        connection.commit()
        self._committed = True

    def rollback(self) -> None:
        connection = self._connection
        if connection is None:
            raise RuntimeError("unit of work is not active")
        connection.rollback()
        self._committed = False
