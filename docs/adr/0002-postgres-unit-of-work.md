# ADR 0002: shared PostgreSQL Unit of Work

## Status

Accepted for v0.3 architecture hardening.

## Context

The v0.3 application boundaries are semantic, but the original PostgreSQL stores opened and
committed their own connections. That is safe for single-store operations but prevents an
application service from enforcing a cross-repository invariant atomically.

Scientific snapshot reads also require repeatable-read semantics and must not be weakened while
introducing a shared transaction boundary.

## Decision

PostgresUnitOfWork owns one PostgreSQL connection configured at REPEATABLE READ and exposes the
operational repositories for supplements, intake, nutrition, and applicability. The repositories
can still open their own connections in standalone mode, or borrow the UnitOfWork connection.

The UnitOfWork is rollback-by-default. Callers must explicitly call commit() after all
cross-repository invariants succeed. An exception or leaving the context without commit() rolls
the shared transaction back.

AccountStore intentionally remains outside this UnitOfWork. Account export requires a dedicated
read-only repeatable-read transaction, while account deletion is a destructive lifecycle boundary
that should not be coupled to ordinary operational mutations.

## Consequences

- Existing runtime behavior remains backward compatible.
- New multi-repository application services can become atomic incrementally.
- Nutrition snapshot isolation remains at least repeatable-read.
- The application layer can migrate away from ticket-named concrete stores without a flag day.
- A later refactor can inject UnitOfWork factories per application command/update rather than
  keeping long-lived database connections.
