CREATE TABLE account_deletion_intents (
    token TEXT PRIMARY KEY CHECK (token ~ '^[0-9a-f]{24}$'),
    user_id UUID NOT NULL UNIQUE
        REFERENCES users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (expires_at > created_at)
);

CREATE INDEX account_deletion_intents_expires_idx
    ON account_deletion_intents(expires_at);
