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


-- Ensure the complete canonical Westeros map exists as selectable destinations.
-- These rows are map records only; no group, lord, or starting assets are created.
INSERT INTO public.castles(name, region, house, is_coastal, active) VALUES
('Castle Black', 'The Wall', 'Night''s Watch', FALSE, TRUE),
('Eastwatch', 'The Wall', 'Night''s Watch', TRUE, TRUE),
('Shadow Tower', 'The Wall', 'Night''s Watch', FALSE, TRUE),
('Winterfell', 'North', 'Stark', FALSE, TRUE),
('The Dreadfort', 'North', 'Bolton', FALSE, TRUE),
('Karhold', 'North', 'Karstark', TRUE, TRUE),
('Riverrun', 'Riverlands', 'Tully', FALSE, TRUE),
('The Twins', 'Riverlands', 'Frey', FALSE, TRUE),
('Seagard', 'Riverlands', 'Mallister', TRUE, TRUE),
('The Eyrie', 'Vale', 'Arryn', FALSE, TRUE),
('Gulltown', 'Vale', 'Grafton', TRUE, TRUE),
('Redfort', 'Vale', 'Redfort', FALSE, TRUE),
('Pyke', 'Iron Islands', 'Greyjoy', TRUE, TRUE),
('Ten Towers', 'Iron Islands', 'Harlaw', TRUE, TRUE),
('Hammerhorn', 'Iron Islands', 'Goodbrother', TRUE, TRUE),
('Casterly Rock', 'Westerlands', 'Lannister', TRUE, TRUE),
('Hornvale', 'Westerlands', 'Brax', FALSE, TRUE),
('Ashemark', 'Westerlands', 'Marbrand', FALSE, TRUE),
('King''s Landing', 'Crownlands', 'Crownlands', TRUE, TRUE),
('Dragonstone', 'Crownlands', 'Targaryen', TRUE, TRUE),
('Sharp Point', 'Crownlands', 'Bar Emmon', TRUE, TRUE),
('Storm''s End', 'Stormlands', 'Baratheon', TRUE, TRUE),
('Fellwood', 'Stormlands', 'Fell', FALSE, TRUE),
('Blackhaven', 'Stormlands', 'Dondarrion', FALSE, TRUE),
('Highgarden', 'Reach', 'Tyrell', FALSE, TRUE),
('Horn Hill', 'Reach', 'Tarly', FALSE, TRUE),
('Oldtown', 'Reach', 'Hightower', TRUE, TRUE),
('Sunspear', 'Dorne', 'Martell', TRUE, TRUE),
('Kingsgrave', 'Dorne', 'Manwoody', FALSE, TRUE),
('Yronwood', 'Dorne', 'Yronwood', TRUE, TRUE)
ON CONFLICT (name) DO NOTHING;

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
