# Changelog
## 0.2.0 — standalone prototype bundle
- Added Telegram polling bootstrap, menus, lord creation, resource collection, trades, statements and basic admin commands.
- Added PostgreSQL persistence models.
- Added Windows setup and start scripts.
- Backup/restore remains intentionally disabled pending verified implementation.
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
