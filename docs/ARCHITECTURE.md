# Architecture

## Baseline

KIR-108 establishes infrastructure and project structure only. It intentionally does not implement Telegram flows, nutrient calculations, or scientific constants.

Current repository layout:

```text
.github/
  workflows/
docs/
src/
  vitaminbot/
tests/
docker-compose.yml
pyproject.toml
```

## Planned application boundaries

Future work should preserve clear boundaries between:

- **Telegram adapter**: transport-specific command/update handling.
- **Application services**: use-case orchestration independent of Telegram transport.
- **Domain contracts**: canonical nutrient, ingredient, serving, unit, and provenance models governed by their assigned Linear work.
- **Safety validation**: deterministic policy evaluation governed by the safety/scientific lane.
- **Persistence**: PostgreSQL-backed durable application state and migrations.
- **Scheduling/reminders**: durable reminder definitions and delivery coordination.
- **Caching/coordination**: Redis only where it provides a documented application need.

These are boundaries, not permissions to implement work outside an assigned Linear issue.

## Runtime baseline

- Python: 3.12
- PostgreSQL: Docker Compose service based on PostgreSQL 16 Alpine
- Redis: Docker Compose service based on Redis 7 Alpine
- Packaging: `pyproject.toml` with a `src/` layout
- Quality gates: Ruff lint/format, Mypy, and Pytest
- CI: GitHub Actions on pull requests and pushes to `main`

## Configuration

Runtime configuration is read from environment variables. `.env.example` documents local variable names and placeholder values; real `.env` files are ignored by Git. Credentials and production secrets must not be committed.

## Safety design principle

Application infrastructure must not silently substitute guessed scientific values. Safety-critical evaluation is expected to be deterministic and fail closed when governed inputs are absent, invalid, ambiguous, or outside their documented applicability.
