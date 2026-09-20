# KIR-112 PostgreSQL persistence

## Boundaries

The schema persists the accepted KIR-109 domain contract without redefining scientific truth.

Canonical products and formulation versions are separate from user-tracked supplement instances. Intake plans and planned events are separate from consumed intake events. Candidate records remain separate from confirmed canonical data, and unknown values remain nullable rather than using zero as a sentinel.

## Privacy and deletion

The user table is the ownership root for profile, tracked-supplement, plan, intake-event, and candidate-resolution data. Foreign-key cascades make complete removal of those user-owned records technically possible. Canonical product and source records are not owned by the user row and therefore are not silently destroyed by account deletion.

The MVP profile stores only technical locale/timezone fields needed by application behavior. It does not pre-create medication, pregnancy, kidney/liver, or other speculative health columns.

No generic audit table copies sensitive payloads. Corrections to intake history are explicit through entered-in-error and corrects-event lineage while both rows remain until a governed deletion removes the user-owned history.

## Provenance and revision

Source records are versioned and may link supersession. Product formulations are versioned rows with explicit source links. Derived amount metadata stores rule identity/version, authority source, and input amount lineage. The migration contains no dose targets, UL values, reference values, interaction thresholds, or scientific conversion coefficients.

## Migrations

Packaged SQL migrations are discovered in version order. The migration runner:

- serializes concurrent migration processes with a PostgreSQL advisory lock;
- applies each migration transactionally;
- records version, name, and SHA-256 checksum;
- refuses to continue if an already-applied migration has changed;
- is safe to re-run after a process restart.

Run with DATABASE_URL configured:

    python -m vitaminbot.persistence.migrations

DATABASE_SCHEMA can select an alternate schema for isolated tests.

## CI PostgreSQL tests

The mandatory Linux CI lane starts the repository PostgreSQL Compose service with CI-only credentials, waits for readiness, executes the full pytest suite against PostgreSQL, and always tears the service and volumes down. The Windows compatibility lane remains non-blocking under the accepted KIR-123 least-privilege deferral.
