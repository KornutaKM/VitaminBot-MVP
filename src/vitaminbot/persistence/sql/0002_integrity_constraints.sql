ALTER TABLE user_supplements
    ADD CONSTRAINT user_supplements_instance_formulation_key
    UNIQUE (instance_id, formulation_id);

ALTER TABLE intake_plans
    ADD COLUMN formulation_id TEXT;

UPDATE intake_plans AS plan
SET formulation_id = supplement.formulation_id
FROM user_supplements AS supplement
WHERE supplement.instance_id = plan.tracked_instance_id;

ALTER TABLE intake_plans
    ALTER COLUMN formulation_id SET NOT NULL,
    ADD CONSTRAINT intake_plans_plan_version_formulation_key
        UNIQUE (plan_id, version, formulation_id),
    ADD CONSTRAINT intake_plans_instance_formulation_fkey
        FOREIGN KEY (tracked_instance_id, formulation_id)
        REFERENCES user_supplements(instance_id, formulation_id)
        ON DELETE CASCADE;

ALTER TABLE planned_intake_events
    ADD COLUMN formulation_id TEXT;

UPDATE planned_intake_events AS event
SET formulation_id = plan.formulation_id
FROM intake_plans AS plan
WHERE plan.plan_id = event.plan_id
  AND plan.version = event.plan_version;

ALTER TABLE planned_intake_events
    ALTER COLUMN formulation_id SET NOT NULL,
    ADD CONSTRAINT planned_events_plan_formulation_fkey
        FOREIGN KEY (plan_id, plan_version, formulation_id)
        REFERENCES intake_plans(plan_id, version, formulation_id)
        ON DELETE CASCADE,
    ADD CONSTRAINT planned_events_unit_formulation_fkey
        FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT;

ALTER TABLE intake_events
    ADD COLUMN formulation_id TEXT;

UPDATE intake_events AS event
SET formulation_id = supplement.formulation_id
FROM user_supplements AS supplement
WHERE supplement.instance_id = event.tracked_instance_id;

ALTER TABLE intake_events
    ALTER COLUMN formulation_id SET NOT NULL,
    ADD CONSTRAINT intake_events_event_instance_key
        UNIQUE (event_id, tracked_instance_id),
    ADD CONSTRAINT intake_events_instance_formulation_fkey
        FOREIGN KEY (tracked_instance_id, formulation_id)
        REFERENCES user_supplements(instance_id, formulation_id)
        ON DELETE CASCADE,
    ADD CONSTRAINT intake_events_unit_formulation_fkey
        FOREIGN KEY (formulation_id, consumption_unit_id)
        REFERENCES consumption_units(formulation_id, unit_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT intake_events_correction_same_instance_fkey
        FOREIGN KEY (corrects_event_id, tracked_instance_id)
        REFERENCES intake_events(event_id, tracked_instance_id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE FUNCTION enforce_formulation_has_source()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_formulation_id TEXT;
BEGIN
    IF TG_TABLE_NAME = 'product_formulations' THEN
        target_formulation_id := NEW.formulation_id;
    ELSE
        target_formulation_id := OLD.formulation_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM product_formulations
        WHERE formulation_id = target_formulation_id
    )
       AND NOT EXISTS (
        SELECT 1
        FROM formulation_sources
        WHERE formulation_id = target_formulation_id
    )
    THEN
        RAISE EXCEPTION
            'product formulation must retain at least one provenance source'
            USING ERRCODE = '23514';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER product_formulation_requires_source
AFTER INSERT OR UPDATE ON product_formulations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_formulation_has_source();

CREATE CONSTRAINT TRIGGER formulation_source_cardinality
AFTER DELETE OR UPDATE ON formulation_sources
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_formulation_has_source();

CREATE FUNCTION enforce_derived_amount_has_input()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_formulation_id TEXT;
    target_amount_id TEXT;
    target_evidence_status TEXT;
BEGIN
    IF TG_TABLE_NAME = 'product_amounts' THEN
        target_formulation_id := NEW.formulation_id;
        target_amount_id := NEW.amount_id;
    ELSE
        target_formulation_id := OLD.formulation_id;
        target_amount_id := OLD.amount_id;
    END IF;

    SELECT evidence_status
    INTO target_evidence_status
    FROM product_amounts
    WHERE formulation_id = target_formulation_id
      AND amount_id = target_amount_id;

    IF target_evidence_status = 'derived'
       AND NOT EXISTS (
            SELECT 1
            FROM amount_derivation_inputs
            WHERE formulation_id = target_formulation_id
              AND amount_id = target_amount_id
       )
    THEN
        RAISE EXCEPTION
            'derived amount must retain at least one input amount'
            USING ERRCODE = '23514';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER derived_amount_requires_input
AFTER INSERT OR UPDATE ON product_amounts
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_derived_amount_has_input();

CREATE CONSTRAINT TRIGGER derivation_input_cardinality
AFTER DELETE OR UPDATE ON amount_derivation_inputs
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_derived_amount_has_input();

CREATE FUNCTION enforce_candidate_resolution_has_candidate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_candidate_set_id TEXT;
BEGIN
    IF TG_TABLE_NAME = 'candidate_resolutions' THEN
        target_candidate_set_id := NEW.candidate_set_id;
    ELSE
        target_candidate_set_id := OLD.candidate_set_id;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM candidate_resolutions
        WHERE candidate_set_id = target_candidate_set_id
    )
       AND NOT EXISTS (
        SELECT 1
        FROM entity_candidates
        WHERE candidate_set_id = target_candidate_set_id
    )
    THEN
        RAISE EXCEPTION
            'candidate resolution must retain at least one candidate'
            USING ERRCODE = '23514';
    END IF;

    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER candidate_resolution_requires_candidate
AFTER INSERT OR UPDATE ON candidate_resolutions
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_candidate_resolution_has_candidate();

CREATE CONSTRAINT TRIGGER candidate_cardinality
AFTER DELETE OR UPDATE ON entity_candidates
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION enforce_candidate_resolution_has_candidate();

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM product_formulations AS formulation
        WHERE NOT EXISTS (
            SELECT 1
            FROM formulation_sources AS source
            WHERE source.formulation_id = formulation.formulation_id
        )
    ) THEN
        RAISE EXCEPTION
            'existing product formulation lacks provenance source'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM product_amounts AS amount
        WHERE amount.evidence_status = 'derived'
          AND NOT EXISTS (
              SELECT 1
              FROM amount_derivation_inputs AS input
              WHERE input.formulation_id = amount.formulation_id
                AND input.amount_id = amount.amount_id
          )
    ) THEN
        RAISE EXCEPTION
            'existing derived amount lacks input lineage'
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM candidate_resolutions AS resolution
        WHERE NOT EXISTS (
            SELECT 1
            FROM entity_candidates AS candidate
            WHERE candidate.candidate_set_id = resolution.candidate_set_id
        )
    ) THEN
        RAISE EXCEPTION
            'existing candidate resolution lacks retained candidate'
            USING ERRCODE = '23514';
    END IF;
END;
$$;
