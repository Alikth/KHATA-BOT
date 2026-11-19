BEGIN;
-- Remove obsolete cross-system synchronization scaffolding. The bot now runs
-- exclusively against its own PostgreSQL database.
DROP TABLE IF EXISTS integration_inbox;
DROP TABLE IF EXISTS integration_outbox;
DROP TABLE IF EXISTS integration_sync_state;
INSERT INTO schema_version(version) VALUES (4) ON CONFLICT DO NOTHING;
COMMIT;
