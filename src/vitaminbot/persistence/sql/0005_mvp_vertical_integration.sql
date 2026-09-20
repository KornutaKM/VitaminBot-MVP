CREATE TABLE kir122_composition_sessions (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (state IN ('amount_input', 'amount_review')),
    tracked_instance_id TEXT NOT NULL,
    formulation_id TEXT NOT NULL,
    serving_basis_id TEXT NOT NULL,
    consumption_unit_id TEXT NOT NULL,
    expected_supplement_revision BIGINT NOT NULL CHECK (expected_supplement_revision >= 1),
    substance_key TEXT NOT NULL CHECK (btrim(substance_key) <> ''),
    analyte_id TEXT NOT NULL CHECK (btrim(analyte_id) <> ''),
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    pending_value NUMERIC,
    pending_unit TEXT CHECK (pending_unit IS NULL OR pending_unit IN ('g', 'mg', 'ug')),
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tracked_instance_id, user_id)
        REFERENCES user_supplements(instance_id, user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tracked_instance_id, formulation_id)
        REFERENCES user_supplements(instance_id, formulation_id)
        ON DELETE CASCADE,
    FOREIGN KEY (formulation_id, serving_basis_id)
        REFERENCES product_servings(formulation_id, basis_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT,
    CHECK ((pending_value IS NULL) = (pending_unit IS NULL)),
    CHECK (pending_value IS NULL OR pending_value >= 0),
    CHECK (
        (state = 'amount_input' AND pending_value IS NULL)
        OR (state = 'amount_review' AND pending_value IS NOT NULL)
    )
);

CREATE TABLE kir122_manual_amounts (
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    tracked_instance_id TEXT NOT NULL,
    formulation_id TEXT NOT NULL,
    amount_id TEXT NOT NULL,
    substance_key TEXT NOT NULL CHECK (btrim(substance_key) <> ''),
    analyte_id TEXT NOT NULL CHECK (btrim(analyte_id) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tracked_instance_id, substance_key),
    UNIQUE (amount_id),
    FOREIGN KEY (tracked_instance_id, user_id)
        REFERENCES user_supplements(instance_id, user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tracked_instance_id, formulation_id)
        REFERENCES user_supplements(instance_id, formulation_id)
        ON DELETE CASCADE,
    FOREIGN KEY (formulation_id, amount_id)
        REFERENCES product_amounts(formulation_id, amount_id)
        ON DELETE CASCADE
);

CREATE INDEX kir122_manual_amounts_user_idx
    ON kir122_manual_amounts(user_id, tracked_instance_id);


CREATE TABLE kir122_confirmed_label_records (
    idempotency_key TEXT PRIMARY KEY CHECK (btrim(idempotency_key) <> ''),
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL CHECK (btrim(candidate_id) <> ''),
    extraction_payload JSONB NOT NULL,
    provider_key TEXT NOT NULL CHECK (btrim(provider_key) <> ''),
    model_revision TEXT NOT NULL CHECK (btrim(model_revision) <> ''),
    adapter_revision TEXT NOT NULL CHECK (btrim(adapter_revision) <> ''),
    prompt_revision TEXT NOT NULL CHECK (btrim(prompt_revision) <> ''),
    schema_revision TEXT NOT NULL CHECK (btrim(schema_revision) <> ''),
    preprocessing_revision TEXT NOT NULL CHECK (btrim(preprocessing_revision) <> ''),
    image_sha256 TEXT NOT NULL CHECK (image_sha256 ~ '^[0-9A-Fa-f]{64}$'),
    raw_response_sha256 TEXT
        CHECK (
            raw_response_sha256 IS NULL
            OR raw_response_sha256 ~ '^[0-9A-Fa-f]{64}$'
        ),
    requested_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, candidate_id),
    CHECK (completed_at >= requested_at),
    CHECK (confirmed_at >= completed_at)
);

CREATE INDEX kir122_confirmed_label_records_user_idx
    ON kir122_confirmed_label_records(user_id, confirmed_at DESC);
