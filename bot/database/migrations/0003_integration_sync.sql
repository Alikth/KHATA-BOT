BEGIN;
CREATE TABLE IF NOT EXISTS integration_inbox (
  operation_id VARCHAR(80) PRIMARY KEY,
  source VARCHAR(32) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS integration_outbox (
  operation_id VARCHAR(80) PRIMARY KEY,
  aggregate_type VARCHAR(40) NOT NULL,
  aggregate_key VARCHAR(120) NOT NULL,
  event_type VARCHAR(80) NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_integration_outbox_pending
  ON integration_outbox(created_at) WHERE delivered_at IS NULL;
CREATE TABLE IF NOT EXISTS integration_sync_state (
  key VARCHAR(80) PRIMARY KEY,
  value JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_version(version) VALUES (3) ON CONFLICT DO NOTHING;
COMMIT;
