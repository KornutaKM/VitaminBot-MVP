ALTER TABLE planned_intake_events
    ADD COLUMN schedule_kind TEXT NOT NULL DEFAULT 'routine_bucket'
        CHECK (schedule_kind IN ('routine_bucket', 'explicit_time')),
    ADD COLUMN local_time TIME,
    ADD CONSTRAINT planned_intake_events_schedule_shape CHECK (
        (
            schedule_kind = 'routine_bucket'
            AND local_time IS NULL
            AND (
                schedule_label IS NULL
                OR schedule_label IN ('morning', 'day', 'evening')
            )
        )
        OR (
            schedule_kind = 'explicit_time'
            AND schedule_label = 'explicit_time'
            AND local_time IS NOT NULL
        )
    );

ALTER TABLE user_supplements
    ADD CONSTRAINT user_supplements_instance_user_key
    UNIQUE (instance_id, user_id);

CREATE TABLE reminder_occurrences (
    occurrence_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    tracked_instance_id TEXT NOT NULL,
    formulation_id TEXT NOT NULL,
    plan_id TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    planned_event_id TEXT NOT NULL,
    consumption_unit_id TEXT NOT NULL,
    consumption_units NUMERIC NOT NULL CHECK (consumption_units > 0),
    schedule_kind TEXT NOT NULL CHECK (
        schedule_kind IN ('routine_bucket', 'explicit_time')
    ),
    schedule_label TEXT NOT NULL CHECK (btrim(schedule_label) <> ''),
    timezone TEXT NOT NULL CHECK (btrim(timezone) <> ''),
    local_date DATE NOT NULL,
    scheduled_local_time TIME NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (
        state IN ('pending', 'taken', 'skipped', 'needs_review')
    ),
    later_count SMALLINT NOT NULL DEFAULT 0 CHECK (
        later_count >= 0 AND later_count <= 1
    ),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tracked_instance_id, local_date),
    FOREIGN KEY (tracked_instance_id, user_id)
        REFERENCES user_supplements(instance_id, user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tracked_instance_id, formulation_id)
        REFERENCES user_supplements(instance_id, formulation_id)
        ON DELETE CASCADE,
    FOREIGN KEY (plan_id, plan_version, planned_event_id)
        REFERENCES planned_intake_events(plan_id, plan_version, event_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT,
    CHECK (due_at >= scheduled_at OR later_count = 1)
);

CREATE INDEX reminder_occurrences_due_idx
    ON reminder_occurrences(state, due_at);

CREATE TABLE reminder_delivery_attempts (
    delivery_id TEXT PRIMARY KEY,
    occurrence_id TEXT NOT NULL
        REFERENCES reminder_occurrences(occurrence_id) ON DELETE CASCADE,
    occurrence_revision BIGINT NOT NULL CHECK (occurrence_revision >= 1),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    attempt_number SMALLINT NOT NULL CHECK (
        attempt_number >= 1 AND attempt_number <= 3
    ),
    status TEXT NOT NULL CHECK (
        status IN ('claimed', 'sent', 'failed', 'uncertain', 'cancelled')
    ),
    lease_expires_at TIMESTAMPTZ,
    provider_message_id TEXT,
    failure_code TEXT,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    CHECK (provider_message_id IS NULL OR btrim(provider_message_id) <> ''),
    CHECK (failure_code IS NULL OR btrim(failure_code) <> ''),
    CHECK (
        (status = 'claimed' AND lease_expires_at IS NOT NULL AND completed_at IS NULL)
        OR (status <> 'claimed' AND completed_at IS NOT NULL)
    )
);

CREATE INDEX reminder_delivery_occurrence_idx
    ON reminder_delivery_attempts(occurrence_id, occurrence_revision, status);

CREATE TABLE occurrence_actions (
    action_id TEXT PRIMARY KEY,
    occurrence_id TEXT NOT NULL
        REFERENCES reminder_occurrences(occurrence_id) ON DELETE CASCADE,
    action_kind TEXT NOT NULL CHECK (
        action_kind IN ('taken', 'later', 'skip', 'correction')
    ),
    idempotency_key TEXT NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    occurrence_revision BIGINT NOT NULL CHECK (occurrence_revision >= 1),
    later_until TIMESTAMPTZ,
    intake_event_id TEXT
        REFERENCES intake_events(event_id) ON DELETE CASCADE,
    corrects_action_id TEXT
        REFERENCES occurrence_actions(action_id)
        ON DELETE CASCADE
        DEFERRABLE INITIALLY DEFERRED,
    entered_in_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (action_kind = 'later' AND later_until IS NOT NULL)
        OR (action_kind <> 'later' AND later_until IS NULL)
    ),
    CHECK (
        (action_kind = 'taken' AND intake_event_id IS NOT NULL)
        OR (action_kind <> 'taken' AND intake_event_id IS NULL)
    ),
    CHECK (
        (action_kind = 'correction' AND corrects_action_id IS NOT NULL)
        OR (action_kind <> 'correction' AND corrects_action_id IS NULL)
    )
);

CREATE INDEX occurrence_actions_occurrence_idx
    ON occurrence_actions(occurrence_id, created_at);

CREATE TABLE schedule_edit_sessions (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    tracked_instance_id TEXT NOT NULL,
    expected_plan_revision BIGINT NOT NULL CHECK (expected_plan_revision >= 1),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tracked_instance_id, user_id)
        REFERENCES user_supplements(instance_id, user_id)
        ON DELETE CASCADE
);
