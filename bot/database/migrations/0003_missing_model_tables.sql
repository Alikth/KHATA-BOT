BEGIN;

CREATE TABLE IF NOT EXISTS castle_production (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  production_key VARCHAR(80) NOT NULL,
  level INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT uq_castle_production UNIQUE (castle_id, production_key)
);
CREATE TABLE IF NOT EXISTS castle_camps (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  camp_key VARCHAR(80) NOT NULL,
  level INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT uq_castle_camp UNIQUE (castle_id, camp_key)
);
CREATE TABLE IF NOT EXISTS castle_special_camps (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  camp_key VARCHAR(80) NOT NULL,
  level INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT uq_castle_special_camp UNIQUE (castle_id, camp_key)
);
CREATE TABLE IF NOT EXISTS castle_army (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  unit_key VARCHAR(80) NOT NULL,
  count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
  CONSTRAINT uq_castle_army_unit UNIQUE (castle_id, unit_key)
);
CREATE TABLE IF NOT EXISTS castle_equipment (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  item_key VARCHAR(80) NOT NULL,
  count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
  CONSTRAINT uq_castle_equipment UNIQUE (castle_id, item_key)
);
CREATE TABLE IF NOT EXISTS castle_fleet (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  ship_key VARCHAR(40) NOT NULL,
  count INTEGER NOT NULL DEFAULT 0 CHECK (count >= 0),
  CONSTRAINT uq_castle_fleet UNIQUE (castle_id, ship_key)
);
CREATE TABLE IF NOT EXISTS castle_economy_state (
  castle_id BIGINT PRIMARY KEY REFERENCES castles(id) ON DELETE CASCADE,
  workshop_level INTEGER NOT NULL DEFAULT 0,
  port_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  port_level INTEGER NOT NULL DEFAULT 0,
  last_week_key VARCHAR(16),
  food_debt INTEGER NOT NULL DEFAULT 0,
  food_debt_due_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS admin_login_attempts (
  telegram_user_id BIGINT PRIMARY KEY,
  failures INTEGER NOT NULL DEFAULT 0,
  locked_until TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS castle_equipment_limits (
  id BIGSERIAL PRIMARY KEY,
  castle_id BIGINT NOT NULL REFERENCES castles(id) ON DELETE CASCADE,
  tracker_key VARCHAR(120) NOT NULL,
  used INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT uq_equipment_limit_tracker UNIQUE (castle_id, tracker_key)
);

INSERT INTO schema_version(version) VALUES (3) ON CONFLICT DO NOTHING;
COMMIT;
