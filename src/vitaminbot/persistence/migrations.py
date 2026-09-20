from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from importlib.resources import files
from typing import Any

import psycopg
from psycopg import Connection, sql

_MIGRATION_PATTERN = re.compile(r"^(?P<version>\\d{4})_(?P<name>[a-z0-9_]+)\\.sql$")
_LOCK_NAMESPACE = "vitaminbot-schema-migrations"


class MigrationError(RuntimeError):
    """Base error for deterministic migration failures."""


class MigrationDriftError(MigrationError):
    """Raised when an already-applied migration no longer matches its checksum."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str
    checksum: str


def discover_migrations() -> tuple[Migration, ...]:
    """Load packaged SQL migrations in strict version order."""
    discovered: list[Migration] = []
    seen_versions: set[str] = set()

    for resource in files("vitaminbot.persistence.sql").iterdir():
        match = _MIGRATION_PATTERN.fullmatch(resource.name)
        if match is None:
            continue

        version = match.group("version")
        if version in seen_versions:
            raise MigrationError(f"duplicate migration version: {version}")
        seen_versions.add(version)

        migration_sql = resource.read_text(encoding="utf-8")
        checksum = hashlib.sha256(migration_sql.encode("utf-8")).hexdigest()
        discovered.append(
            Migration(
                version=version,
                name=match.group("name"),
                sql=migration_sql,
                checksum=checksum,
            )
        )

    discovered.sort(key=lambda migration: migration.version)
    if not discovered:
        raise MigrationError("no packaged migrations were discovered")
    return tuple(discovered)


def _prepare_schema(conn: Connection[Any], schema: str) -> None:
    if not schema.strip():
        raise MigrationError("schema must not be blank")

    if schema != "public":
        conn.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
        )
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))


def _ensure_tracking_table(conn: Connection[Any]) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def migrate(database_url: str, *, schema: str = "public") -> tuple[str, ...]:
    """Apply pending migrations with checksum verification and an advisory lock.

    Each migration is committed independently. A crash cannot mark a failed migration
    as applied, and a later process can safely resume from the last committed version.
    """
    migrations = discover_migrations()
    applied_now: list[str] = []
    lock_key = f"{_LOCK_NAMESPACE}:{schema}"

    with psycopg.connect(database_url, autocommit=True) as conn:
        _prepare_schema(conn, schema)
        conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
        try:
            _ensure_tracking_table(conn)

            for migration in migrations:
                existing = conn.execute(
                    "SELECT name, checksum FROM schema_migrations WHERE version = %s",
                    (migration.version,),
                ).fetchone()
                if existing is not None:
                    existing_name, existing_checksum = existing
                    if (
                        existing_name != migration.name
                        or existing_checksum != migration.checksum
                    ):
                        raise MigrationDriftError(
                            f"migration {migration.version} differs from applied checksum"
                        )
                    continue

                with conn.transaction():
                    conn.execute(migration.sql, prepare=False)
                    conn.execute(
                        """
                        INSERT INTO schema_migrations (version, name, checksum)
                        VALUES (%s, %s, %s)
                        """,
                        (migration.version, migration.name, migration.checksum),
                    )
                applied_now.append(migration.version)
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_key,))

    return tuple(applied_now)


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    schema = os.getenv("DATABASE_SCHEMA", "public")
    applied = migrate(database_url, schema=schema)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
    else:
        print("Database schema is current")


if __name__ == "__main__":
    main()
