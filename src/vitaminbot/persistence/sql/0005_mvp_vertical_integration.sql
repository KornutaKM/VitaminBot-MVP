CREATE TABLE kir122_nutrient_entry_sessions (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    tracked_instance_id TEXT NOT NULL
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    state TEXT NOT NULL
        CHECK (state IN ('nutrient_name', 'nutrient_value', 'nutrient_unit', 'nutrient_review')),
    substance_key TEXT,
    subject_kind TEXT,
    subject_id TEXT,
    amount_basis TEXT,
    equivalence_basis TEXT,
    display_name TEXT,
    pending_value NUMERIC,
    pending_unit TEXT,
    expected_supplement_revision INTEGER NOT NULL
        CHECK (expected_supplement_revision >= 1),
    revision INTEGER NOT NULL DEFAULT 1
        CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (state = 'nutrient_name'
            AND substance_key IS NULL
            AND subject_kind IS NULL
            AND subject_id IS NULL
            AND amount_basis IS NULL
            AND equivalence_basis IS NULL
            AND display_name IS NULL
            AND pending_value IS NULL
            AND pending_unit IS NULL)
        OR
        (state = 'nutrient_value'
            AND substance_key IS NOT NULL
            AND subject_kind IS NOT NULL
            AND subject_id IS NOT NULL
            AND amount_basis IS NOT NULL
            AND display_name IS NOT NULL
            AND pending_value IS NULL
            AND pending_unit IS NULL)
        OR
        (state = 'nutrient_unit'
            AND substance_key IS NOT NULL
            AND subject_kind IS NOT NULL
            AND subject_id IS NOT NULL
            AND amount_basis IS NOT NULL
            AND display_name IS NOT NULL
            AND pending_value IS NOT NULL
            AND pending_unit IS NULL)
        OR
        (state = 'nutrient_review'
            AND substance_key IS NOT NULL
            AND subject_kind IS NOT NULL
            AND subject_id IS NOT NULL
            AND amount_basis IS NOT NULL
            AND display_name IS NOT NULL
            AND pending_value IS NOT NULL
            AND pending_unit IS NOT NULL)
    )
);

CREATE INDEX kir122_nutrient_entry_sessions_instance_idx
    ON kir122_nutrient_entry_sessions(tracked_instance_id);
