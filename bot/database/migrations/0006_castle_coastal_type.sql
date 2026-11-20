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

UPDATE public.castle_economy_state AS economy
SET port_enabled = TRUE
FROM public.castles AS castle
WHERE economy.castle_id = castle.id
  AND castle.is_coastal = TRUE;

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
