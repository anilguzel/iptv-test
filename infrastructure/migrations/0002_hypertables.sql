-- OPTIONAL: run AFTER the services have started once (so the tables exist) to
-- convert the high-volume time-series tables into TimescaleDB hypertables:
--
--   docker compose exec postgres \
--     psql -U bist -d bist -f /docker-entrypoint-initdb.d/0002_hypertables.sql
--
-- Safe to re-run: migrate_data moves any existing rows, if_not_exists skips
-- tables that are already hypertables. No-op on plain Postgres (the function
-- will not exist there) — the app works fine either way.
SELECT create_hypertable('market_ticks', 'market_timestamp', if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('intraday_points', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('flow_snapshots', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
SELECT create_hypertable('ohlcv', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE);
