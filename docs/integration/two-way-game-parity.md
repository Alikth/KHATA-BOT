# Two-way game parity: architecture and data mapping

Status: implementation in progress. The service bridge, D1 event capture, PostgreSQL snapshot consumer, asset report, superuser identity correction, siege guards and food-debt settlement are implemented on the feature branch. Live data has not been migrated or overwritten.

## Non-negotiable requirements

- Keep Cloudflare D1 and PostgreSQL as two independent databases.
- Give the website and Telegram bot the same player/admin capabilities and game rules.
- Do not add bot registration or a website-account-linking flow.
- Preserve superuser assignment through `set lord`, using Telegram numeric user IDs.
- Preserve current website accounts and ownership records; do not equate website account IDs with Telegram IDs.
- A game action in either interface must become visible in the other after durable synchronization.
- Battle outcomes remain admin-adjudicated.

## Current PostgreSQL bot model

The current bot schema includes:
- Identity and Telegram metadata: `castles`, `lords`, `group_registrations`.
- Economy: `resource_balances`, `castle_economy_state`.
- Assets: `castle_assets`, `castle_production`, `castle_camps`, `castle_special_camps`, `castle_army`, `castle_equipment`, `castle_fleet`.
- Game operations: `trade_offers`, `war_expeditions`, `military_alliances`, `garrison_assets`, `war_scenarios`, `troop_transfer_requests`.
- Scheduling/audit: `game_events`, `game_state`, `game_settings`, `admin_audit_logs`, `equipment_build_limits`.

The website Worker is in the separate `Alikth/KHATA-GAMES` repository. Its D1 economy schema includes `castle_state`, `castle_production`, `castle_camps`, `castle_special_camps`, `castle_army`, `castle_equipment`, `castle_fleet`, `castle_week_state`, `game_week_runs` and `castle_equipment_limits`. Additional Worker-managed domains include trade requests, war logs, garrisons, alliances, scenarios, runtime controls and notifications.

## Confirmed issues from source inspection

1. `create_lord` currently creates new PostgreSQL starting balances. This must be replaced during integration by importing the existing website castle snapshot into the bot mirror; assigning a Lord must never reset the website's current assets.
2. `menu:assets` currently reads only `ResourceBalance`; it omits the complete army/building/camp/equipment/fleet/special-asset inventory.
3. Bot upgrades, trade, war and weekly economy currently mutate PostgreSQL independently of D1.
4. Bot `weekly_settlement` selects the first active Lord for a castle. Website settlement is castle-state based. The bot food-debt casualty helper exists but is not called by the regular overdue-debt settlement cycle.
5. Bot admin detection currently requires owner ID, exact admin chat ID and a group/supergroup chat. It denies admin identity in private chat and other player groups.
6. The Worker website player APIs currently authenticate website sessions; a private bot-to-Worker service-auth contract does not exist.
7. Bot `site_catalog.json` is a static copy. Rule/catalog drift must be detected and versioned.

## Logical mapping

| Aggregate | Website D1 | Bot PostgreSQL | Mapping |
|---|---|---|---|
| Castle | `castle_state` and game catalog | `castles` | Canonical exact castle name; keep local IDs |
| Lord assignment | No Telegram numeric ID in website ownership model | `lords.telegram_user_id`, `lords.castle_id` | Superuser `set lord` assignment; mirror to D1 integration assignment table |
| Telegram group | Website account/group features | `group_registrations` | Bot-specific metadata |
| Resources/debt | `castle_state` and debt fields | `resource_balances`, `castle_economy_state` | Resource key + castle name |
| Production | `castle_production` | `castle_production` | Production key + level |
| Camps | `castle_camps`, `castle_special_camps` | Same-named PostgreSQL tables | Camp key + level |
| Army | `castle_army` | `castle_army` | Unit key + count |
| Equipment/fleet | `castle_equipment`, `castle_fleet` | Same-named PostgreSQL tables | Item/ship key + count |
| Workshop/port/special assets | `castle_state` and related D1 tables | `castle_economy_state`, `castle_assets` | Explicit field mapping; never assume defaults |
| Trade | D1 `trade_requests` and related tables | `trade_offers` | Immutable external operation ID |
| War | D1 `war_logs` and related tables | `war_expeditions`, `war_scenarios`, `troop_transfer_requests` | Immutable external operation ID |
| Alliance/garrison | D1 alliance/garrison tables | `military_alliances`, `garrison_assets` | Canonical castle + external operation ID |
| Audit | Website audit records | `admin_audit_logs` | Shared correlation ID; local audit retained |

## Synchronization protocol

Use durable at-least-once delivery with an outbox/inbox pattern, not a distributed SQL transaction.

1. Each command has a globally unique `operation_id`, `correlation_id`, actor, canonical castle key, aggregate type, expected aggregate version, payload schema version and rules version.
2. The receiving application authenticates and authorizes the actor, validates game rules, siege/locks, available assets and expected version.
3. Commit the local game mutation and outbox event atomically in the source database.
4. The other application consumes events, applies them in a local transaction, and inserts the operation ID into a unique inbox table.
5. Acknowledge only after the local transaction commits. Retries cannot apply the same operation twice.
6. Use per-castle aggregate versions / compare-and-swap. Never use last-write-wins to overwrite newer state.
7. Reconciliation compares canonical snapshots and event cursors, reports conflicts, and requires explicit resolution.
8. Outbox events remain pending during outages and resume after recovery.

### Mutation direction

- Website action: D1 commits the operation and outbox event; bot consumes the event and updates PostgreSQL.
- Bot action: bot validates the Telegram actor against its existing `set lord` assignment, calls a private authenticated Worker endpoint, Worker validates and commits to D1, then bot consumes the resulting event and updates PostgreSQL.
- PostgreSQL remains an independent persistent replica and Telegram metadata store. D1 remains an independent persistent website store.
- Website routes and bot commands must share the same versioned domain rules. Bot-side duplicate rule implementations must not remain authoritative.

## Planned integration schema (not yet applied)

D1:
- `integration_outbox` with operation ID, aggregate key/version, event type, payload, schema/rules version and delivery state.
- `integration_bot_assignments` mapping Telegram numeric ID to canonical castle name and active/revoked assignment. This mirrors `set lord`; it is not account linking.
- Consumer cursors and idempotency records.

PostgreSQL:
- `integration_inbox` with unique operation ID.
- `integration_outbox` where bot-originated Telegram metadata/commands need durable delivery.
- `integration_sync_state` with D1 event cursor and schema/rules compatibility.
- Nullable external operation IDs for trade/war rows, backfilled only after reconciliation.
- Aggregate version tracking for mirrored castle snapshots.

## Safe rollout

1. Complete route/schema inventory in both repositories.
2. Generate read-only per-castle reconciliation report.
3. Add integration schema and service authentication behind disabled feature flags.
4. Add read-only snapshot APIs and verify mapping.
5. Add durable outbox/inbox and idempotent delivery.
6. Verify read parity before enabling writes.
7. Enable bot-originated writes by domain, then website-originated replication.
8. Roll out assets/buildings/camps/economy, then trade, then war.
9. Test concurrency, retries, downtime and recovery.
10. Enable production sync only after parity tests pass.

## Safety

- Never fetch, print, commit, or replace `.env` or live credentials.
- Never seed starting balances over an existing website castle inventory.
- Never resolve conflicting snapshots automatically.
- Never merge this branch into `main` without explicit approval.
- Keep the Telegram proxy PR separate from this feature and verify its status before merging.


## Implemented on the feature branch

- Private Worker service API protected by `BOT_API_SECRET`.
- Superuser assignment mirror through `set lord`; no Telegram account-registration or website-account-linking flow.
- Full D1 castle snapshot endpoint for assigned Telegram lords.
- D1 change outbox and triggers for castle resources, production, camps, army, equipment, fleet and food debt.
- Bot polling consumer that refreshes the PostgreSQL castle mirror from snapshots and persists its event cursor in `game_state`.
- Bot asset menu now includes resources, production buildings, camps, army, equipment, fleet, workshop/port and food debt.
- Bot production/camp upgrades can call the Worker, with siege checks and idempotent operation IDs.
- Superuser identity no longer depends on the current chat ID/type.
- Bot overdue food-debt settlement now applies proportional casualties after the 24-hour deadline and defers during siege.
- Python CI passed `compileall` and `pytest` for the current tested commit.

## Required deployment configuration

1. Generate a long random secret and configure it in Cloudflare Worker secrets as `BOT_API_SECRET` (for example with `npx wrangler secret put BOT_API_SECRET`).
2. Configure the same value in the bot's local, uncommitted `.env` as `SITE_API_SECRET`.
3. Set `SITE_API_URL=https://khata-games.khta.workers.dev` (or the actual deployed Worker origin) and `SITE_API_TIMEOUT_SECONDS=15`.
4. Apply D1 migration `migrations/0006_bot_integration.sql` and PostgreSQL migration `bot/database/migrations/0003_integration_sync.sql` after taking separate verified backups. The Worker also creates its integration tables/triggers idempotently on the first authenticated integration call.
5. Restart the bot, then assign a test lord using `set lord` in a registered castle group. Verify that the D1 snapshot populates PostgreSQL and that a website-side asset change appears in the bot within the polling interval.

Do not copy a real secret into GitHub, chat, source code, or `.env.example`.

## Remaining parity work (not yet complete)

- Bot-originated trade creation/accept/reject/cancel is still PostgreSQL-local; it needs Worker service commands and matching D1 trade records.
- Bot-originated warfare, garrison, alliance, scenario and troop-transfer mutations still need Worker service commands and durable cross-store identifiers.
- The website's player-facing ownership model is still based on website accounts; this integration does not create or link such accounts to Telegram. Telegram assignments are a separate bot authorization mapping.
- Workshop, port, equipment construction and all admin asset mutations still need write-through service endpoints.
- Full read-only reconciliation report for every castle has not yet been generated; do not use a live snapshot to overwrite an existing PostgreSQL castle until that report is reviewed.
- Rules/catalog version drift checks, sync conflict reporting, event acknowledgement/retention, outage recovery tests and live end-to-end tests remain.
- No production deployment or real D1/PostgreSQL migration has been executed by this branch.
