# KHATA-GAMES website source audit (uploaded archive)

Source reviewed: `KHATA-GAMES-main (6).zip`. The website uses Cloudflare Worker + D1 (SQLite), not PostgreSQL. The bot must therefore reproduce game behavior in its own PostgreSQL database; it must not connect to the site's D1 database.

## Exact source-derived catalog

The bot package contains `bot/game/site_catalog.json`, exported from:
- `src/worker/data/game-rules.js`
- `src/worker/data/game-data.js`

The export preserves the site's named production definitions, regional production bonuses, general and special camps, equipment, ship capacity, resource keys/labels, war-lord labels, castle metadata, and house/castle map.

## Website persistence found in migrations and Worker

The uploaded site migrations define `users`, `players`, `sessions`, `castle_state`, `castle_production`, `castle_camps`, `castle_special_camps`, `castle_army`, `castle_equipment`, `castle_fleet`, `game_week_runs`, `castle_week_state`, `castle_equipment_limits`, `rate_limits`, `war_logs`, and `trade_requests`. The Worker also creates/extends runtime tables including `dynamic_castles`, `castle_garrison_assets`, `food_debts`, `military_alliances`, `notifications`, `role_cooldowns`, `role_submissions`, `scenario_submissions`, `game_controls`, `game_runtime`, `game_announcements`, and related control tables.

## Site resource starting state

The source migration `0002_castle_economy.sql` sets the base castle values to: peasants 500, coins 5000, wood 500, stone 500, iron 500, meat 500, fish 500, grain 6000, horses 0, dragon_glass 0, wildfire 0, tar 0, grapes 50. The bot's lord creation now uses these values as its initial balances.

## Feature parity status after warfare/trade integration build

| Website subsystem | Site behavior confirmed in source | Bot implementation in this build |
|---|---|---|
| Accounts and castle ownership | One player account owns a castle; castle groups and lord names are mapped | Telegram account ↔ one lord ↔ one castle/group; owner-only `set lord` |
| Resource/economy | Source migration and game-rules catalog | Website starting resources, production/camps, weekly settlement, food debt and equipment/fleet foundations from prior integration build |
| War expedition | `war_logs`, land/sea selection, asset deductions, duration, arrival and cancellation | `/march`, `/marchgarrison`, `/arrivals`, `/cancelmarch`; world-clock-aware arrival worker |
| Sea transport | `SHIP_CAPACITY={transport:600,warship:400}` and naval checks | Capacity checks use 600/400 and require enabled port |
| War command | Attacker selects attack/siege/deploy after arrival; default command window 90 minutes | `/warcommand`; 90-minute world-clock deadline; deploy places force in garrison |
| Scenario | Attack scenarios for attacker/defender, default 24-hour deadline, one submission per account | `/scenario`; one submission per lord/expedition and 24-hour deadline |
| Battle review | Admin records attacker/defender outcome, then casualties; attacker army/equipment/fleet losses and defender army losses | `/warresolve` in owner admin group records outcome and casualty JSON, validates snapshots, credits survivors |
| Garrison | Owner-specific garrison assets can be viewed and used as a new expedition source | `/garrisons`, `/marchgarrison`; owner-scoped garrison inventory |
| Alliance | Destination lord accepts/rejects; accepted force remains stationed, rejected force returns | `/alliances`, `/alliance`; accepted force stored in owner garrison, rejection returns it |
| Troop transfer | Destination lord accepts/rejects a transfer request | `/transfers`, `/transfer`; accepted force stored at destination as sender-owned garrison, rejected force returns |
| Trade | Multi-resource bundle, excluding peasants, receiver approval | `/tradepack`; resource baskets excluding peasants, receiver approval and trade log |
| Admin views | Site admin reviews wars, scenarios and trades | `/adminwars`, `/adminscenarios`, `/reviewscenario`, `/warresolve`, `/admincastles`, `/admintrades` |

## Remaining parity gaps

This build now contains the requested core war and multi-resource trade workflows, but is not a verified full clone of every site admin/social feature. Still outstanding are site-equivalent trade expiry/cancel/rollback, every game-control lock and admin purchase operation, dynamic-castle management, role/social submissions, private notification inbox, and full regression coverage for every site route. Siege outcome is adjudicated by the owner as in the site's admin-reviewed war flow; no unsupported automatic battle simulator was invented.

## Important implementation note

This audit is based on the uploaded source archive, not a live GitHub connection. Several runtime schemas are created dynamically in Worker code; before claiming complete parity, each route and helper in `src/worker/index.js` and the frontend JS must be mapped and ported with regression tests. The site source is not modified by this project.
