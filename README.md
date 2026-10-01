# VitaminBot MVP

Telegram assistant for supplement tracking, confirmed label/product data, deterministic nutrient aggregation, evidence-backed reference information, scheduling, and safety-oriented validation.

## Project governance

- **Linear** is the source of truth for assignments, scope, status, blockers, gates, dependencies, and exit criteria.
- **GitHub** is the source of truth for code, branches, commits, pull requests, CI, and releases.
- Scientific constants and safety rules require explicit provenance and applicability.
- Numeric safety decisions must be deterministic; LLM output is not the authority for dose calculations or threshold comparisons.
- Implementation work is performed through issue-scoped branches and pull requests. No direct feature development on `main`.

See `docs/PROJECT_CONTROL.md`, `docs/ARCHITECTURE.md`, and `docs/SCIENTIFIC_PROVENANCE.md`.

## Local development

VitaminBot currently targets **Python 3.12**.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate the environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

Run the baseline checks:

```bash
ruff check .
ruff format --check .
mypy src
pytest
```

## PostgreSQL and Redis

Copy the environment template to a local `.env` file and replace placeholder values where appropriate. The real `.env` file is ignored by Git.

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up -d
docker compose ps
```

Stop the services with `docker compose down`. Remove development volumes only when you intentionally want to discard local data: `docker compose down -v`.


Run migrations once, then start the Telegram update process and reminder worker separately:

```bash
vitaminbot-migrate
vitaminbot-bot
```

In a second terminal/process:

```bash
vitaminbot-worker
```

The bot process handles Telegram updates only. The worker owns reminder materialization, durable claiming, revalidation, delivery, and delivery-result persistence. Running multiple bot processes does not start extra reminder loops inside them.
