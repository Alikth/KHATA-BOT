# Test plan

## Unit tests
- Resource arithmetic: no negative balances, precision and bounds.
- Production calculations and upgrade costs.
- Combat formulas, casualties, garrison handling and retreat.
- Expedition timings and pause/resume clock.
- Trade validation, expiry and exactly-once transfer.
- Admin permission checks and password verification.
- Statement validation and publication state machine.

## Integration tests (real PostgreSQL)
- Migrations from an empty database.
- Foreign keys, unique Telegram account, nonnegative resources.
- Concurrent accept of the same trade offer only transfers once.
- Simultaneous asset updates serialize safely.
- Event processor recovers after simulated crash.
- Backup restore into a clean disposable database and record-count verification.

## Regression tests mapped from website behavior
For each transferable game rule, record:
1. Input state and action.
2. Expected resource/army/result changes.
3. Relevant source code and formula.
4. Test proving the bot matches the rule.
Do not copy website data; only behavior and rule definitions are reviewed.

## Release gate
Do not invite real players until migrations, critical game-rule tests, pause/resume,
trade idempotency, admin authorization, and backup/restore tests pass.
