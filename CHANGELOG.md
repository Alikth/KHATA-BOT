# Changelog
## 0.2.0 — standalone prototype bundle
- Added Telegram polling bootstrap, menus, lord creation, resource collection, trades, statements and basic admin commands.
- Added PostgreSQL persistence models.
- Added Windows setup and start scripts.
- Backup and restore are provided by guarded PostgreSQL scripts; a real test restore is still a release requirement.
- Full combat/expedition/equipment/fleet rule parity is not yet complete.

## Integrated economy port
- Resolved stale module/package collisions by moving handler, service, and keyboard implementations into their importable packages.
- Added PostgreSQL models for production, camps, special camps, army, equipment, fleet, economy state, and equipment build limits.
- Added website-catalog-based production/camp upgrades, weekly settlement and food upkeep, workshop/equipment/port commands.
- Added virtual world clock persistence that excludes host downtime.
- Added implementation parity status document and catalog contract tests.

## 2026-11-18 — Warfare and multi-asset integration build
- Added war expedition lifecycle, land/sea transport capacity, arrival processing, cancellation, command window, scenarios, admin battle review, garrisons, alliances, and troop-transfer decisions.
- Added multi-resource trade baskets excluding peasants, with recipient confirmation.
- Added management listings for castles, wars, scenarios, and trades.
- Added PostgreSQL migration `0002_warfare_trade_parity.sql`.
- Added schema contract tests for the warfare and trade models.

## 2026-11-18 — Stability and operations hardening
- Added migration `0003_missing_model_tables.sql` for all ORM tables missing from the initial migrations.
- Removed startup `create_all`; startup now checks the migration version.
- Added ordered migration runner, verified custom-format PostgreSQL backup, SHA-256 verification, and guarded restore to a separate empty database.
- Added PostgreSQL 16 CI covering migrations, ORM schema contract, imports, and unit tests.
- Hardened admin login with persistent failed-attempt lockout and fail-fast configuration checks.
- Hardened trade rules and food-debt credit; added overdue debt casualties and siege restrictions.
- Hardened expedition ownership, sea port checks, two-step deployment, transfer inventory handling, and timeout cancellation with immediate asset return.
- Validated castle registration against the official castle/region/house catalog and supported multi-word castle names in commands.
- Removed tracked `.env` and Python bytecode artifacts.
