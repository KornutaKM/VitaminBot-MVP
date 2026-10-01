ALTER TABLE user_supplements
    ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'active'
        CHECK (lifecycle_status IN ('active', 'paused')),
    ADD COLUMN paused_at TIMESTAMPTZ,
    ADD CONSTRAINT user_supplements_pause_state_check
        CHECK (
            (lifecycle_status = 'active' AND paused_at IS NULL)
            OR (lifecycle_status = 'paused' AND paused_at IS NOT NULL)
        );

ALTER TABLE reminder_occurrences
    ADD COLUMN cancelled_at TIMESTAMPTZ,
    ADD COLUMN cancellation_reason TEXT,
    ADD CONSTRAINT reminder_occurrences_cancellation_check
        CHECK (
            (cancelled_at IS NULL AND cancellation_reason IS NULL)
            OR (
                cancelled_at IS NOT NULL
                AND cancellation_reason IN ('supplement_paused')
            )
        );

CREATE INDEX reminder_occurrences_active_due_idx
    ON reminder_occurrences(state, due_at)
    WHERE cancelled_at IS NULL;
