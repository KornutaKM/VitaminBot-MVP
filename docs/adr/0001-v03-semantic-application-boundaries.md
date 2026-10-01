# ADR 0001: Semantic application boundaries for v0.3

Status: Accepted  
Date: 2026-10-01

## Context

VitaminBot's current application and persistence modules are primarily named after delivery tickets
(`kir116`, `kir120`, `kir122`, `kir146`, `kir174`). Those names are useful for traceability
in Linear, commits, pull requests, and acceptance evidence, but they do not describe the runtime
responsibilities of the code.

The v0.3 product direction centers on four user-facing capabilities:

1. capture and manage supplements;
2. maintain an intake plan and operate the Today loop;
3. aggregate confirmed composition deterministically;
4. request applicability context only when a reference lookup requires it.

The scientific engine remains deterministic. LLM or recognition output must not become an authority
for numeric dose calculations, thresholds, or personalized safety conclusions.

## Decision

Introduce semantic application packages:

- `vitaminbot.application.supplements`
- `vitaminbot.application.intake`
- `vitaminbot.application.nutrition`
- `vitaminbot.application.applicability`

The first migration step is intentionally behavior-preserving. These packages expose semantic names
as compatibility aliases over the accepted ticket-oriented controllers. Existing `kir*.py` modules
remain the implementation source until later pull requests move code by responsibility.

This staged approach separates mechanical architecture changes from behavior changes and keeps the
safety regression surface reviewable.

Ticket identifiers remain in:

- Linear issues;
- commit and pull-request metadata;
- acceptance documentation;
- historical tests where the ticket identity is material.

Ticket identifiers should not be the long-term namespace of production domain/application code.

## Target direction

The intended dependency direction is:

```text
telegram adapter
    -> application use cases
        -> domain / deterministic nutrition + safety
        -> repository protocols / unit of work
            -> postgres implementation
```

Presentation will migrate from application-generated prose to structured view models rendered by the
Telegram adapter. Persistence will migrate from ticket stores to subject-oriented repositories without
rewriting the accepted SQL semantics in the same change.

## Invariants

The migration must preserve:

- fail-closed handling of missing or ambiguous scientific inputs;
- deterministic normalization, aggregation, and reference comparisons;
- immutable/revision-bound computation context;
- no conversion of unknown composition to zero;
- no inferred personalized dose recommendation;
- durable reminder/intake idempotency and correction semantics;
- existing safety regression behavior.

## Consequences

Positive:

- product concepts become discoverable from the package structure;
- future Today/onboarding work can depend on stable semantic imports;
- ticket history no longer dictates runtime architecture;
- migration can proceed in small, independently reviewable PRs.

Trade-offs:

- compatibility aliases temporarily duplicate vocabulary;
- ticket modules remain until their internals are moved;
- import migration alone does not reduce module size.

## Follow-up sequence

1. Migrate Telegram wiring to semantic imports.
2. Introduce structured presentation view models.
3. Split use cases by responsibility behind the semantic packages.
4. Introduce subject-oriented repositories and a unit-of-work boundary.
5. Remove compatibility aliases only after all runtime callers and tests use semantic modules.
