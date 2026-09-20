ALTER TABLE product_servings
    ADD CONSTRAINT product_servings_current_pair_key
    UNIQUE (formulation_id, basis_id, consumption_unit_id);

ALTER TABLE user_supplements
    ADD COLUMN revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    ADD COLUMN current_consumption_unit_id TEXT,
    ADD COLUMN current_serving_basis_id TEXT,
    ADD CONSTRAINT user_supplements_current_unit_fkey
        FOREIGN KEY (formulation_id, current_consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT user_supplements_current_serving_pair_fkey
        FOREIGN KEY (
            formulation_id,
            current_serving_basis_id,
            current_consumption_unit_id
        )
        REFERENCES product_servings (
            formulation_id,
            basis_id,
            consumption_unit_id
        )
        ON DELETE RESTRICT,
    ADD CONSTRAINT user_supplements_current_serving_pair_check
        CHECK (
            (current_consumption_unit_id IS NULL)
            = (current_serving_basis_id IS NULL)
        );

ALTER TABLE intake_plans
    ADD CONSTRAINT intake_plans_instance_version_key
    UNIQUE (plan_id, version, tracked_instance_id);

CREATE TABLE intake_plan_heads (
    tracked_instance_id TEXT PRIMARY KEY
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    plan_id TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (plan_id, plan_version, tracked_instance_id)
        REFERENCES intake_plans(plan_id, version, tracked_instance_id)
        ON DELETE CASCADE
);

CREATE TABLE manual_supplement_drafts (
    draft_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    product_name TEXT,
    unit_label TEXT,
    units_per_serving NUMERIC,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id),
    CHECK (product_name IS NULL OR btrim(product_name) <> ''),
    CHECK (
        unit_label IS NULL
        OR unit_label IN (
            'capsule',
            'tablet',
            'softgel',
            'scoop',
            'drop'
        )
    ),
    CHECK (units_per_serving IS NULL OR units_per_serving > 0)
);

CREATE TABLE bot_sessions (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    state TEXT NOT NULL CHECK (
        state IN (
            'idle',
            'manual_name',
            'manual_unit',
            'manual_serving_quantity',
            'manual_review',
            'plan_quantity',
            'plan_bucket',
            'profile_timezone',
            'profile_locale',
            'edit_name',
            'edit_serving_unit',
            'edit_serving_quantity'
        )
    ),
    draft_id TEXT
        REFERENCES manual_supplement_drafts(draft_id) ON DELETE CASCADE,
    target_instance_id TEXT
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    pending_text TEXT,
    pending_quantity NUMERIC,
    expected_revision BIGINT,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (pending_text IS NULL OR btrim(pending_text) <> ''),
    CHECK (pending_quantity IS NULL OR pending_quantity > 0),
    CHECK (expected_revision IS NULL OR expected_revision >= 0),
    CHECK (
        (state LIKE 'manual_%' AND draft_id IS NOT NULL)
        OR (state NOT LIKE 'manual_%')
    ),
    CHECK (
        (
            state IN (
                'plan_quantity',
                'plan_bucket',
                'edit_name',
                'edit_serving_unit',
                'edit_serving_quantity'
            )
            AND target_instance_id IS NOT NULL
        )
        OR state NOT IN (
            'plan_quantity',
            'plan_bucket',
            'edit_name',
            'edit_serving_unit',
            'edit_serving_quantity'
        )
    )
);

CREATE TABLE bot_action_receipts (
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    action_key TEXT NOT NULL CHECK (btrim(action_key) <> ''),
    action_type TEXT NOT NULL CHECK (btrim(action_type) <> ''),
    result_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, action_key),
    CHECK (result_ref IS NULL OR btrim(result_ref) <> '')
);

CREATE INDEX bot_action_receipts_created_at_idx
    ON bot_action_receipts(created_at);
