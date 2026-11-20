BEGIN;
ALTER TABLE public.castles
    ADD COLUMN IF NOT EXISTS is_coastal BOOLEAN NOT NULL DEFAULT FALSE;

-- Preserve the previous canonical coastal list for castles already registered.
UPDATE public.castles
SET is_coastal = TRUE
WHERE name IN (
    'Eastwatch', 'Karhold', 'Seagard', 'Gulltown', 'Pyke',
    'Ten Towers', 'Hammerhorn', 'Casterly Rock', 'King''s Landing',
    'Dragonstone', 'Sharp Point', 'Storm''s End', 'Oldtown',
    'Sunspear', 'Yronwood'
);

INSERT INTO public.castle_economy_state(
    castle_id, workshop_level, port_enabled, port_level, food_debt
)
SELECT castle.id, 0, TRUE, 0, 0
FROM public.castles AS castle
WHERE castle.is_coastal = TRUE
ON CONFLICT (castle_id) DO UPDATE SET port_enabled = TRUE;

-- Seed a basic fleet only when a coastal castle has no row for that ship yet.
INSERT INTO public.castle_fleet(castle_id, ship_key, count)
SELECT castle.id, 'transport', 1
FROM public.castles AS castle
WHERE castle.is_coastal = TRUE
ON CONFLICT (castle_id, ship_key) DO NOTHING;

INSERT INTO public.castle_fleet(castle_id, ship_key, count)
SELECT castle.id, 'warship', 1
FROM public.castles AS castle
WHERE castle.is_coastal = TRUE
ON CONFLICT (castle_id, ship_key) DO NOTHING;

INSERT INTO public.schema_version(version)
VALUES (6)
ON CONFLICT DO NOTHING;
COMMIT;
