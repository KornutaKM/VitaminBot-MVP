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
        );

ALTER TABLE bot_sessions
    DROP CONSTRAINT bot_sessions_check4,
    ADD CONSTRAINT bot_sessions_check4
        CHECK (
            (
                state IN (
                    'plan_quantity',
                    'plan_bucket',
                    'edit_name',
                    'edit_serving_unit',
                    'edit_serving_quantity',
                    'composition_serving_quantity'
                )
                AND target_instance_id IS NOT NULL
            )
            OR state NOT IN (
                'plan_quantity',
                'plan_bucket',
                'edit_name',
                'edit_serving_unit',
                'edit_serving_quantity',
                'composition_serving_quantity'
            )
        );
