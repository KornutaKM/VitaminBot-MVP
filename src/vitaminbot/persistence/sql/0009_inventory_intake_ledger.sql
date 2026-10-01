ALTER TABLE supplement_inventory
    ADD COLUMN needs_reconciliation BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE inventory_events (
    event_id TEXT PRIMARY KEY,
    tracked_instance_id TEXT NOT NULL
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    consumption_unit_id TEXT NOT NULL,
    event_kind TEXT NOT NULL CHECK (
        event_kind IN ('manual_set', 'intake_decrement', 'intake_correction')
    ),
    quantity_units NUMERIC NOT NULL CHECK (quantity_units >= 0),
    balance_before NUMERIC,
    balance_after NUMERIC NOT NULL CHECK (balance_after >= 0),
    needs_reconciliation_before BOOLEAN,
    inventory_revision_after BIGINT NOT NULL CHECK (inventory_revision_after >= 1),
    intake_event_id TEXT
        REFERENCES intake_events(event_id) ON DELETE CASCADE,
    related_event_id TEXT
        REFERENCES inventory_events(event_id) ON DELETE CASCADE,
    balance_applied BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX inventory_events_intake_kind_key
    ON inventory_events(intake_event_id, event_kind)
    WHERE intake_event_id IS NOT NULL;
