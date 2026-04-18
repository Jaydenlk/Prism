INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Generating static SQL
INFO  [alembic.runtime.migration] Will assume transactional DDL.
BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

INFO  [alembic.runtime.migration] Running upgrade  -> 001, Initial 19-table schema for Prism v2
-- Running upgrade  -> 001

CREATE TABLE users (
    id VARCHAR(36) NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    username VARCHAR(50) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    role VARCHAR(20) DEFAULT 'user' NOT NULL, 
    avatar_url VARCHAR(500), 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_users_email UNIQUE (email), 
    CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE TABLE invite_codes (
    id VARCHAR(36) NOT NULL, 
    code VARCHAR(20) NOT NULL, 
    created_by VARCHAR(36) NOT NULL, 
    max_uses INTEGER DEFAULT '1' NOT NULL, 
    used_count INTEGER DEFAULT '0' NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_invite_codes_code UNIQUE (code), 
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE providers (
    id VARCHAR(36) NOT NULL, 
    scope VARCHAR(20) DEFAULT 'user' NOT NULL, 
    user_id VARCHAR(36), 
    name VARCHAR(100) NOT NULL, 
    protocol VARCHAR(20) NOT NULL, 
    base_url VARCHAR(500) NOT NULL, 
    api_key_encrypted TEXT NOT NULL, 
    model_id VARCHAR(100) NOT NULL, 
    is_default BOOLEAN DEFAULT 'false' NOT NULL, 
    priority INTEGER DEFAULT '0' NOT NULL, 
    is_healthy BOOLEAN DEFAULT 'true' NOT NULL, 
    config JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_providers_scope_user_id CHECK ((scope = 'system' AND user_id IS NULL) OR (scope = 'user' AND user_id IS NOT NULL)), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_providers_scope_user_default ON providers (scope, user_id, is_default);

CREATE INDEX ix_providers_scope_user_priority ON providers (scope, user_id, priority);

CREATE TABLE mcp_servers (
    id VARCHAR(36) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    description TEXT, 
    scope VARCHAR(20) DEFAULT 'system' NOT NULL, 
    command VARCHAR(500) NOT NULL, 
    args JSONB DEFAULT '[]' NOT NULL, 
    env JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
);

CREATE TABLE im_channel_configs (
    id VARCHAR(36) NOT NULL, 
    channel VARCHAR(50) NOT NULL, 
    is_enabled BOOLEAN DEFAULT 'false' NOT NULL, 
    config JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_im_channel_configs_channel UNIQUE (channel)
);

CREATE TABLE sessions (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    title VARCHAR(200), 
    status VARCHAR(20) DEFAULT 'idle' NOT NULL, 
    blocking_run_id VARCHAR(36), 
    config_snapshot JSONB DEFAULT '{}' NOT NULL, 
    is_pinned BOOLEAN DEFAULT 'false' NOT NULL, 
    pinned_at TIMESTAMP WITH TIME ZONE, 
    im_channel VARCHAR(50), 
    im_chat_id VARCHAR(200), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_sessions_user_updated ON sessions (user_id, updated_at);

CREATE INDEX ix_sessions_user_pinned_updated ON sessions (user_id, is_pinned, updated_at);

CREATE TABLE session_queue_items (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    prompt TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'queued' NOT NULL, 
    sequence_no INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE
);

CREATE INDEX ix_session_queue_items_session_status_seq ON session_queue_items (session_id, status, sequence_no);

CREATE TABLE runs (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    prompt TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    model VARCHAR(100) NOT NULL, 
    provider_id VARCHAR(36), 
    schedule_mode VARCHAR(20) DEFAULT 'immediate' NOT NULL, 
    error_message TEXT, 
    input_tokens INTEGER, 
    output_tokens INTEGER, 
    cache_hit_tokens INTEGER, 
    cache_miss_tokens INTEGER, 
    cache_creation_tokens INTEGER, 
    cost_usd NUMERIC(10, 6), 
    turn_count INTEGER, 
    agent_type VARCHAR(50), 
    run_mode VARCHAR(20) DEFAULT 'foreground' NOT NULL, 
    parent_run_id VARCHAR(36), 
    harness_version VARCHAR(20), 
    harness_summary JSONB, 
    started_at TIMESTAMP WITH TIME ZONE, 
    finished_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(provider_id) REFERENCES providers (id), 
    FOREIGN KEY(parent_run_id) REFERENCES runs (id)
);

CREATE INDEX ix_runs_session_created ON runs (session_id, created_at);

CREATE INDEX ix_runs_user_created ON runs (user_id, created_at);

CREATE INDEX ix_runs_status_pending ON runs (status) WHERE status = 'pending';

ALTER TABLE sessions ADD CONSTRAINT fk_sessions_blocking_run_id FOREIGN KEY(blocking_run_id) REFERENCES runs (id) ON DELETE SET NULL;

CREATE TABLE messages (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    run_id VARCHAR(36), 
    role VARCHAR(20) NOT NULL, 
    content JSONB NOT NULL, 
    text_preview VARCHAR(500), 
    sequence_no INTEGER NOT NULL, 
    is_skill_context BOOLEAN DEFAULT 'false' NOT NULL, 
    skill_name VARCHAR(200), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
    FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_messages_session_seq ON messages (session_id, sequence_no);

CREATE INDEX ix_messages_run_id ON messages (run_id);

CREATE TABLE tool_executions (
    id VARCHAR(36) NOT NULL, 
    session_id VARCHAR(36) NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    tool_name VARCHAR(100) NOT NULL, 
    input JSONB NOT NULL, 
    output JSONB, 
    is_error BOOLEAN DEFAULT 'false' NOT NULL, 
    duration_ms INTEGER, 
    permission_decision VARCHAR(20), 
    hook_modified BOOLEAN DEFAULT 'false' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE CASCADE, 
    FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE
);

CREATE TABLE coordinator_plans (
    id VARCHAR(36) NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    plan_json JSONB NOT NULL, 
    current_step_index INTEGER DEFAULT '0' NOT NULL, 
    step_results JSONB DEFAULT '[]' NOT NULL, 
    status VARCHAR(20) DEFAULT 'running' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE
);

CREATE INDEX ix_coordinator_plans_run_id ON coordinator_plans (run_id);

CREATE INDEX ix_coordinator_plans_status_updated ON coordinator_plans (status, updated_at);

CREATE TABLE permission_requests (
    id VARCHAR(36) NOT NULL, 
    request_id VARCHAR(36) NOT NULL, 
    run_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    tool_name VARCHAR(100) NOT NULL, 
    tool_input JSONB NOT NULL, 
    reason TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    answered_at TIMESTAMP WITH TIME ZONE, 
    timeout_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_permission_requests_request_id UNIQUE (request_id), 
    FOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_permission_requests_run_status ON permission_requests (run_id, status);

CREATE INDEX ix_permission_requests_status_timeout ON permission_requests (status, timeout_at);

CREATE TABLE user_mcp_installs (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    mcp_server_id VARCHAR(36) NOT NULL, 
    is_enabled BOOLEAN DEFAULT 'true' NOT NULL, 
    config_override JSONB DEFAULT '{}' NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_user_mcp_installs UNIQUE (user_id, mcp_server_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    FOREIGN KEY(mcp_server_id) REFERENCES mcp_servers (id) ON DELETE CASCADE
);

CREATE TABLE im_bindings (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    channel VARCHAR(50) NOT NULL, 
    platform_user_id VARCHAR(200) NOT NULL, 
    platform_chat_id VARCHAR(200) DEFAULT '' NOT NULL, 
    display_name VARCHAR(100), 
    pairing_code VARCHAR(10), 
    paired_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_im_bindings_channel_user_chat UNIQUE (channel, platform_user_id, platform_chat_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE im_message_dedup (
    id VARCHAR(36) NOT NULL, 
    channel VARCHAR(50) NOT NULL, 
    platform_message_id VARCHAR(200) NOT NULL, 
    received_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    session_id VARCHAR(36), 
    PRIMARY KEY (id), 
    CONSTRAINT uq_im_message_dedup_channel_msg UNIQUE (channel, platform_message_id), 
    FOREIGN KEY(session_id) REFERENCES sessions (id)
);

CREATE INDEX ix_im_message_dedup_received_at ON im_message_dedup (received_at);

CREATE TABLE audit_logs (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36), 
    action VARCHAR(100) NOT NULL, 
    resource_type VARCHAR(50), 
    resource_id VARCHAR(36), 
    details JSONB DEFAULT '{}' NOT NULL, 
    ip_address VARCHAR(45), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_audit_logs_user_created ON audit_logs (user_id, created_at);

CREATE INDEX ix_audit_logs_action_created ON audit_logs (action, created_at);

CREATE TABLE skill_installs (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    skill_name VARCHAR(200) NOT NULL, 
    source VARCHAR(50) NOT NULL, 
    source_url VARCHAR(500), 
    version VARCHAR(50) NOT NULL, 
    installed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    metadata JSONB DEFAULT '{}' NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_skill_installs_user_skill UNIQUE (user_id, skill_name), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_skill_installs_user_installed ON skill_installs (user_id, installed_at);

CREATE TABLE user_memories (
    id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    memory_text TEXT NOT NULL, 
    version INTEGER DEFAULT '1' NOT NULL, 
    updated_by VARCHAR(20) NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_user_memories_user_id UNIQUE (user_id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

INSERT INTO alembic_version (version_num) VALUES ('001') RETURNING alembic_version.version_num;

COMMIT;

