# Database migrations

Migration SQL files are versioned and append-only. Never edit a migration after it has been applied to a real database; create a new migration instead.

Before applying a migration to a real game database:
1. Make a verified backup.
2. Apply to a disposable PostgreSQL database.
3. Run schema and integration tests.
4. Check foreign keys, indexes and constraints.
5. Apply to the game database during a controlled stop.


## Migration 0005 — expedition return

Before running the bot with the new expedition UI, apply `0005_expedition_return.sql` to the bot's PostgreSQL database. It adds `war_expeditions.return_after_arrival`; `Base.metadata.create_all` does not add columns to existing tables. Take a verified backup first and apply the migration during a controlled stop. Do not run this migration against the website database.

## Migration 0006 — coastal castle type

Apply `0006_castle_coastal_type.sql` to the bot PostgreSQL database before running this build. It adds `castles.is_coastal`, preserves the prior known coastal-castle list, and seeds the 30 canonical Westeros map castles as selectable destinations without creating groups, lords, resource balances, or starting armies. Coastal map castles receive an enabled port state and one transport ship plus one warship as their initial fleet. A seeded castle can later be attached to a Telegram group through `/registercastle`. Newly registered castles must specify `sea` or `land`. Inland castles cannot use ports or naval expeditions. Do not run this migration against the website database.
