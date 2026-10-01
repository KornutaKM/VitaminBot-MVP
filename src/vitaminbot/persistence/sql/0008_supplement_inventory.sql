CREATE TABLE supplement_inventory (
    tracked_instance_id TEXT PRIMARY KEY
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    formulation_id TEXT NOT NULL,
    consumption_unit_id TEXT NOT NULL,
    remaining_units NUMERIC NOT NULL CHECK (remaining_units >= 0),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT
);

CREATE TABLE inventory_edit_sessions (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    tracked_instance_id TEXT NOT NULL
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    expected_supplement_revision BIGINT NOT NULL CHECK (expected_supplement_revision >= 1),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
