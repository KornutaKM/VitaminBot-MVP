CREATE TABLE users (
    user_id UUID PRIMARY KEY,
    telegram_user_id BIGINT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY
        REFERENCES users(user_id) ON DELETE CASCADE,
    timezone TEXT,
    locale TEXT,
    profile_version BIGINT NOT NULL DEFAULT 1 CHECK (profile_version >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (timezone IS NULL OR btrim(timezone) <> ''),
    CHECK (locale IS NULL OR btrim(locale) <> '')
);

CREATE TABLE source_records (
    source_id TEXT PRIMARY KEY,
    authority TEXT NOT NULL CHECK (btrim(authority) <> ''),
    source_type TEXT NOT NULL CHECK (
        source_type IN (
            'eu_law',
            'efsa_opinion',
            'official_guidance',
            'product_label',
            'secondary_authoritative',
            'chemical_ontology',
            'user_declaration'
        )
    ),
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    stable_identifier TEXT NOT NULL CHECK (btrim(stable_identifier) <> ''),
    version TEXT NOT NULL CHECK (btrim(version) <> ''),
    retrieved_on DATE NOT NULL,
    jurisdiction_code TEXT,
    jurisdiction_parent_code TEXT,
    url TEXT,
    published_on DATE,
    adopted_on DATE,
    effective_on DATE,
    locator TEXT,
    supersedes_source_id TEXT
        REFERENCES source_records(source_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    superseded_by_source_id TEXT
        REFERENCES source_records(source_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (authority, source_type, stable_identifier, version),
    CHECK (jurisdiction_parent_code IS NULL OR jurisdiction_code IS NOT NULL),
    CHECK (url IS NULL OR btrim(url) <> ''),
    CHECK (locator IS NULL OR btrim(locator) <> ''),
    CHECK (supersedes_source_id IS NULL OR supersedes_source_id <> source_id),
    CHECK (superseded_by_source_id IS NULL OR superseded_by_source_id <> source_id)
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (btrim(name) <> ''),
    brand TEXT,
    variant TEXT,
    market_jurisdiction_status TEXT NOT NULL CHECK (
        market_jurisdiction_status IN (
            'resolved',
            'unknown',
            'ambiguous',
            'unresolved_identity'
        )
    ),
    market_jurisdiction_code TEXT,
    market_jurisdiction_parent_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (brand IS NULL OR btrim(brand) <> ''),
    CHECK (variant IS NULL OR btrim(variant) <> ''),
    CHECK (
        (
            market_jurisdiction_status = 'resolved'
            AND market_jurisdiction_code IS NOT NULL
        )
        OR (
            market_jurisdiction_status <> 'resolved'
            AND market_jurisdiction_code IS NULL
            AND market_jurisdiction_parent_code IS NULL
        )
    ),
    CHECK (
        market_jurisdiction_parent_code IS NULL
        OR market_jurisdiction_code IS NOT NULL
    )
);

CREATE TABLE product_formulations (
    formulation_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
    version TEXT NOT NULL CHECK (btrim(version) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (product_id, version)
);

CREATE TABLE formulation_sources (
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE CASCADE,
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    PRIMARY KEY (formulation_id, source_id)
);

CREATE TABLE tracked_analytes (
    analyte_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tracked_analyte_aliases (
    analyte_id TEXT NOT NULL
        REFERENCES tracked_analytes(analyte_id) ON DELETE CASCADE,
    alias TEXT NOT NULL CHECK (btrim(alias) <> ''),
    PRIMARY KEY (analyte_id, alias)
);

CREATE TABLE chemical_forms (
    chemical_form_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    identity_status TEXT NOT NULL CHECK (
        identity_status IN (
            'resolved',
            'unknown',
            'ambiguous',
            'unresolved_identity'
        )
    ),
    external_identifier TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        external_identifier IS NULL
        OR btrim(external_identifier) <> ''
    )
);

CREATE TABLE ingredients (
    ingredient_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    chemical_form_id TEXT
        REFERENCES chemical_forms(chemical_form_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE formulation_ingredients (
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE CASCADE,
    ingredient_id TEXT NOT NULL
        REFERENCES ingredients(ingredient_id) ON DELETE RESTRICT,
    PRIMARY KEY (formulation_id, ingredient_id)
);

CREATE TABLE supply_relationships (
    relationship_id TEXT PRIMARY KEY,
    ingredient_id TEXT NOT NULL
        REFERENCES ingredients(ingredient_id) ON DELETE RESTRICT,
    analyte_id TEXT NOT NULL
        REFERENCES tracked_analytes(analyte_id) ON DELETE RESTRICT,
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    chemical_form_id TEXT
        REFERENCES chemical_forms(chemical_form_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE consumption_units (
    unit_id TEXT PRIMARY KEY,
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE CASCADE,
    label_name TEXT NOT NULL CHECK (btrim(label_name) <> ''),
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formulation_id, unit_id)
);

CREATE TABLE product_servings (
    basis_id TEXT PRIMARY KEY,
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE CASCADE,
    basis_type TEXT NOT NULL CHECK (
        basis_type IN (
            'per_consumption_unit',
            'per_label_portion',
            'per_recommended_daily_portion',
            'per_100_g',
            'per_100_ml',
            'per_day',
            'absolute',
            'other_explicit'
        )
    ),
    label_text TEXT NOT NULL CHECK (btrim(label_text) <> ''),
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    basis_quantity NUMERIC,
    basis_unit TEXT CHECK (
        basis_unit IS NULL OR basis_unit IN ('g', 'mg', 'ug', 'L', 'mL', 'count', 'IU')
    ),
    consumption_unit_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formulation_id, basis_id),
    FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT,
    CHECK ((basis_quantity IS NULL) = (basis_unit IS NULL)),
    CHECK (basis_quantity IS NULL OR basis_quantity > 0),
    CHECK (basis_unit <> 'count' OR consumption_unit_id IS NOT NULL),
    CHECK (
        basis_type <> 'per_consumption_unit'
        OR consumption_unit_id IS NOT NULL
    )
);

CREATE TABLE product_amounts (
    amount_id TEXT PRIMARY KEY,
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE CASCADE,
    subject_kind TEXT NOT NULL CHECK (subject_kind IN ('analyte', 'ingredient')),
    analyte_id TEXT
        REFERENCES tracked_analytes(analyte_id) ON DELETE RESTRICT,
    ingredient_id TEXT
        REFERENCES ingredients(ingredient_id) ON DELETE RESTRICT,
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    resolution_status TEXT NOT NULL CHECK (
        resolution_status IN (
            'resolved',
            'unknown',
            'ambiguous',
            'unresolved_identity'
        )
    ),
    evidence_status TEXT NOT NULL CHECK (
        evidence_status IN ('declared', 'derived', 'ambiguous', 'unknown')
    ),
    value NUMERIC,
    unit TEXT CHECK (
        unit IS NULL OR unit IN ('g', 'mg', 'ug', 'L', 'mL', 'count', 'IU')
    ),
    amount_basis TEXT CHECK (
        amount_basis IS NULL OR amount_basis IN (
            'analyte',
            'elemental',
            'ingredient_compound',
            'material',
            'equivalent'
        )
    ),
    quantity_basis TEXT CHECK (
        quantity_basis IS NULL OR quantity_basis IN (
            'per_consumption_unit',
            'per_label_portion',
            'per_recommended_daily_portion',
            'per_100_g',
            'per_100_ml',
            'per_day',
            'absolute',
            'other_explicit'
        )
    ),
    quantity_basis_id TEXT,
    equivalence_basis TEXT,
    raw_text TEXT,
    derivation_rule_id TEXT,
    derivation_rule_version TEXT,
    derivation_authority_source_id TEXT
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (formulation_id, amount_id),
    FOREIGN KEY (formulation_id, quantity_basis_id)
        REFERENCES product_servings(formulation_id, basis_id)
        ON DELETE RESTRICT,
    CHECK (value IS NULL OR value >= 0),
    CHECK (raw_text IS NULL OR btrim(raw_text) <> ''),
    CHECK (
        (
            subject_kind = 'analyte'
            AND analyte_id IS NOT NULL
            AND ingredient_id IS NULL
        )
        OR (
            subject_kind = 'ingredient'
            AND ingredient_id IS NOT NULL
            AND analyte_id IS NULL
        )
    ),
    CHECK (
        amount_basis IS NULL
        OR (
            amount_basis IN ('analyte', 'elemental', 'equivalent')
            AND subject_kind = 'analyte'
        )
        OR (
            amount_basis IN ('ingredient_compound', 'material')
            AND subject_kind = 'ingredient'
        )
    ),
    CHECK (
        resolution_status <> 'resolved'
        OR (
            value IS NOT NULL
            AND unit IS NOT NULL
            AND amount_basis IS NOT NULL
            AND quantity_basis IS NOT NULL
            AND evidence_status NOT IN ('ambiguous', 'unknown')
        )
    ),
    CHECK (
        resolution_status <> 'resolved'
        OR quantity_basis NOT IN (
            'per_consumption_unit',
            'per_label_portion',
            'per_recommended_daily_portion'
        )
        OR quantity_basis_id IS NOT NULL
    ),
    CHECK (
        (
            amount_basis = 'equivalent'
            AND equivalence_basis IS NOT NULL
            AND btrim(equivalence_basis) <> ''
        )
        OR (
            amount_basis IS DISTINCT FROM 'equivalent'
            AND equivalence_basis IS NULL
        )
    ),
    CHECK (
        (
            evidence_status = 'derived'
            AND resolution_status = 'resolved'
            AND derivation_rule_id IS NOT NULL
            AND btrim(derivation_rule_id) <> ''
            AND derivation_rule_version IS NOT NULL
            AND btrim(derivation_rule_version) <> ''
            AND derivation_authority_source_id IS NOT NULL
        )
        OR (
            evidence_status <> 'derived'
            AND derivation_rule_id IS NULL
            AND derivation_rule_version IS NULL
            AND derivation_authority_source_id IS NULL
        )
    )
);

CREATE TABLE amount_derivation_inputs (
    formulation_id TEXT NOT NULL,
    amount_id TEXT NOT NULL,
    input_amount_id TEXT NOT NULL,
    PRIMARY KEY (formulation_id, amount_id, input_amount_id),
    FOREIGN KEY (formulation_id, amount_id)
        REFERENCES product_amounts(formulation_id, amount_id)
        ON DELETE CASCADE,
    FOREIGN KEY (formulation_id, input_amount_id)
        REFERENCES product_amounts(formulation_id, amount_id)
        ON DELETE RESTRICT,
    CHECK (amount_id <> input_amount_id)
);

CREATE TABLE user_supplements (
    instance_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    formulation_id TEXT NOT NULL
        REFERENCES product_formulations(formulation_id) ON DELETE RESTRICT,
    container_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (container_label IS NULL OR btrim(container_label) <> '')
);

CREATE INDEX user_supplements_user_id_idx
    ON user_supplements(user_id);

CREATE TABLE intake_plans (
    plan_id TEXT NOT NULL,
    version TEXT NOT NULL CHECK (btrim(version) <> ''),
    tracked_instance_id TEXT NOT NULL
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plan_id, version)
);

CREATE INDEX intake_plans_instance_idx
    ON intake_plans(tracked_instance_id);

CREATE TABLE planned_intake_events (
    plan_id TEXT NOT NULL,
    plan_version TEXT NOT NULL,
    event_id TEXT NOT NULL,
    consumption_unit_id TEXT NOT NULL
        REFERENCES consumption_units(unit_id) ON DELETE RESTRICT,
    consumption_units NUMERIC NOT NULL CHECK (consumption_units > 0),
    schedule_label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (plan_id, plan_version, event_id),
    FOREIGN KEY (plan_id, plan_version)
        REFERENCES intake_plans(plan_id, version) ON DELETE CASCADE,
    CHECK (schedule_label IS NULL OR btrim(schedule_label) <> '')
);

CREATE TABLE intake_events (
    event_id TEXT PRIMARY KEY,
    tracked_instance_id TEXT NOT NULL
        REFERENCES user_supplements(instance_id) ON DELETE CASCADE,
    consumption_unit_id TEXT NOT NULL
        REFERENCES consumption_units(unit_id) ON DELETE RESTRICT,
    consumption_units NUMERIC NOT NULL CHECK (consumption_units > 0),
    consumed_at TIMESTAMPTZ NOT NULL,
    confirmation_source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    idempotency_key TEXT UNIQUE,
    corrects_event_id TEXT
        REFERENCES intake_events(event_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED,
    entered_in_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (idempotency_key IS NULL OR btrim(idempotency_key) <> ''),
    CHECK (corrects_event_id IS NULL OR corrects_event_id <> event_id)
);

CREATE INDEX intake_events_instance_time_idx
    ON intake_events(tracked_instance_id, consumed_at);

CREATE TABLE candidate_resolutions (
    candidate_set_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL
        REFERENCES users(user_id) ON DELETE CASCADE,
    confirmation_state TEXT NOT NULL CHECK (
        confirmation_state IN ('unconfirmed', 'confirmed', 'rejected')
    ),
    scientific_resolution_state TEXT NOT NULL CHECK (
        scientific_resolution_state IN ('not_evaluated', 'unresolved', 'resolved')
    ),
    selected_candidate_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (confirmation_state = 'confirmed' AND selected_candidate_id IS NOT NULL)
        OR (confirmation_state <> 'confirmed' AND selected_candidate_id IS NULL)
    )
);

CREATE INDEX candidate_resolutions_user_idx
    ON candidate_resolutions(user_id);

CREATE TABLE entity_candidates (
    candidate_set_id TEXT NOT NULL
        REFERENCES candidate_resolutions(candidate_set_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL,
    canonical_entity_id TEXT NOT NULL CHECK (btrim(canonical_entity_id) <> ''),
    source_id TEXT NOT NULL
        REFERENCES source_records(source_id) ON DELETE RESTRICT,
    state TEXT NOT NULL CHECK (state IN ('active', 'excluded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (candidate_set_id, candidate_id)
);

ALTER TABLE candidate_resolutions
    ADD CONSTRAINT candidate_resolutions_selected_candidate_fk
    FOREIGN KEY (candidate_set_id, selected_candidate_id)
    REFERENCES entity_candidates(candidate_set_id, candidate_id)
    DEFERRABLE INITIALLY DEFERRED;
