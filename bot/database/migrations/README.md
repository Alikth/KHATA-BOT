# Database migrations

Migration SQL files are versioned and append-only. Never edit a migration after it has been applied to a real database; create a new migration instead.

Before applying a migration to a real game database:
1. Make a verified backup.
2. Apply to a disposable PostgreSQL database.
3. Run schema and integration tests.
4. Check foreign keys, indexes and constraints.
5. Apply to the game database during a controlled stop.
