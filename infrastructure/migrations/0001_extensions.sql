-- Runs automatically on first Postgres boot (docker-entrypoint-initdb.d).
-- Enables TimescaleDB. Application tables are created by SQLAlchemy on service
-- startup (init_db); convert the time-series tables to hypertables afterwards
-- with 0002_hypertables.sql.
CREATE EXTENSION IF NOT EXISTS timescaledb;
