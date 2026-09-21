CREATE TABLE user_applicability_profiles (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    completed_months INTEGER,
    completed_years INTEGER,
    sex_applicability TEXT,
    life_stage TEXT,
    physiological_condition TEXT,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (completed_months IS NULL OR (completed_months >= 0 AND completed_months < 24)),
    CHECK (completed_years IS NULL OR completed_years >= 2),
    CHECK (NOT (completed_months IS NOT NULL AND completed_years IS NOT NULL)),
    CHECK (sex_applicability IS NULL OR sex_applicability IN ('male', 'female')),
    CHECK (life_stage IS NULL OR life_stage IN ('general', 'pregnancy', 'lactation')),
    CHECK (
        physiological_condition IS NULL
        OR physiological_condition IN ('premenopausal', 'postmenopausal')
    )
);

CREATE TABLE iron_exposure_applicability (
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    scope_key TEXT NOT NULL CHECK (btrim(scope_key) <> ''),
    under_medical_supervision BOOLEAN,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, scope_key)
);
