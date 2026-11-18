BEGIN;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS expedition_type VARCHAR(12) NOT NULL DEFAULT 'land';
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS asset_origin VARCHAR(16) NOT NULL DEFAULT 'castle';
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS assets JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS defender_assets JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS command VARCHAR(16);
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS command_at TIMESTAMPTZ;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS scenario_deadline_at TIMESTAMPTZ;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS arrival_choice VARCHAR(20);
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS outcome VARCHAR(16);
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS casualties JSONB;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS lord_present BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE war_expeditions ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS offered_assets JSONB;
ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS requested_assets JSONB;
CREATE TABLE IF NOT EXISTS military_alliances (
 id BIGSERIAL PRIMARY KEY, castle_a_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE RESTRICT,
 castle_b_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE RESTRICT,
 owner_a_lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT,
 owner_b_lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT,
 status VARCHAR(16) NOT NULL DEFAULT 'pending', war_expedition_id BIGINT REFERENCES war_expeditions(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), responded_at TIMESTAMPTZ,
 UNIQUE(castle_a_id,castle_b_id));
CREATE TABLE IF NOT EXISTS garrison_assets (
 id BIGSERIAL PRIMARY KEY, castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
 owner_lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT,
 asset_kind VARCHAR(16) NOT NULL, asset_key VARCHAR(80) NOT NULL, count INTEGER NOT NULL DEFAULT 0 CHECK(count>=0),
 UNIQUE(castle_id,owner_lord_id,asset_kind,asset_key));
CREATE TABLE IF NOT EXISTS war_scenarios (
 id BIGSERIAL PRIMARY KEY, expedition_id BIGINT NOT NULL REFERENCES war_expeditions(id) ON DELETE CASCADE,
 lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT, scenario_text TEXT NOT NULL,
 reviewed BOOLEAN NOT NULL DEFAULT FALSE, review_result TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 reviewed_at TIMESTAMPTZ, UNIQUE(expedition_id,lord_id));
CREATE TABLE IF NOT EXISTS troop_transfer_requests (
 id BIGSERIAL PRIMARY KEY, expedition_id BIGINT NOT NULL UNIQUE REFERENCES war_expeditions(id) ON DELETE CASCADE,
 sender_lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT,
 receiver_lord_id BIGINT NOT NULL REFERENCES lords(id) ON DELETE RESTRICT,
 assets JSONB NOT NULL DEFAULT '{}'::jsonb, status VARCHAR(16) NOT NULL DEFAULT 'pending',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), responded_at TIMESTAMPTZ);
INSERT INTO schema_version(version) VALUES (2) ON CONFLICT DO NOTHING;
COMMIT;
