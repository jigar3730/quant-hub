-- Quant Hub v1 schema

CREATE TABLE IF NOT EXISTS scan_runs (
    id BIGSERIAL PRIMARY KEY,
    scan_date DATE NOT NULL,
    scan_time TIMESTAMPTZ NOT NULL,
    strategy_id VARCHAR(32) NOT NULL,
    universe_id VARCHAR(64) NOT NULL,
    universe_size INT,
    tier1_count INT,
    tier2_count INT,
    tier3_count INT,
    filtered_count INT,
    actionable_count INT,
    regime_label VARCHAR(32),
    regime_multiplier DOUBLE PRECISION,
    metadata JSONB,
    UNIQUE (scan_date, strategy_id, universe_id)
);

CREATE TABLE IF NOT EXISTS ticker_results (
    run_id BIGINT REFERENCES scan_runs(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    eligible BOOLEAN,
    tier VARCHAR(32),
    sector_etf VARCHAR(16),
    final_score DOUBLE PRECISION,
    filter_reason TEXT,
    detail JSONB,
    PRIMARY KEY (run_id, ticker)
);

CREATE TABLE IF NOT EXISTS job_runs (
    id BIGSERIAL PRIMARY KEY,
    job_name VARCHAR(128),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status VARCHAR(16),
    tickers_requested INT,
    tickers_fetched INT,
    tickers_failed INT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_runs_date ON scan_runs (scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_job_runs_started ON job_runs (started_at DESC);
