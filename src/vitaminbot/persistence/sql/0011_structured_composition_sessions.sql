ALTER TABLE bot_sessions
    DROP CONSTRAINT bot_sessions_state_check,
    ADD CONSTRAINT bot_sessions_state_check
        CHECK (
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
                'edit_serving_quantity',
                'composition_serving_quantity'
            )
        ),
    ADD CONSTRAINT bot_sessions_composition_target_check
        CHECK (
            state <> 'composition_serving_quantity'
            OR target_instance_id IS NOT NULL
        );
