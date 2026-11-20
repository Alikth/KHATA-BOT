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

INSERT INTO public.schema_version(version)
VALUES (6)
ON CONFLICT DO NOTHING;
COMMIT;
