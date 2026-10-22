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
CREATE INDEX IF NOT EXISTS idx_scan_runs_strategy_universe_date
    ON scan_runs (strategy_id, universe_id, scan_date DESC);
CREATE INDEX IF NOT EXISTS idx_ticker_results_ticker ON ticker_results (ticker);
CREATE INDEX IF NOT EXISTS idx_job_runs_started ON job_runs (started_at DESC);

-- ML foundation: forward-return labels per signal (Phase 1)
CREATE TABLE IF NOT EXISTS signal_outcomes (
    run_id BIGINT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    horizon_days INT NOT NULL,
    anchor_date DATE NOT NULL,
    forward_return_pct DOUBLE PRECISION,
    forward_max_gain_pct DOUBLE PRECISION,
    forward_max_drawdown_pct DOUBLE PRECISION,
    spy_forward_return_pct DOUBLE PRECISION,
    excess_return_pct DOUBLE PRECISION,
    label_binary BOOLEAN,
    label_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, ticker, horizon_days)
);

CREATE INDEX IF NOT EXISTS idx_signal_outcomes_run ON signal_outcomes (run_id);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_status ON signal_outcomes (label_status);
CREATE INDEX IF NOT EXISTS idx_signal_outcomes_anchor ON signal_outcomes (anchor_date DESC);

-- ML Phase 2: trained model registry
CREATE TABLE IF NOT EXISTS ml_models (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    strategy_id VARCHAR(32) NOT NULL,
    universe_id VARCHAR(64) NOT NULL,
    horizon_days INT NOT NULL,
    feature_schema_version VARCHAR(16) NOT NULL,
    model_type VARCHAR(64) NOT NULL,
    train_params JSONB,
    metrics JSONB,
    feature_columns JSONB,
    artifact_path TEXT NOT NULL,
    train_since DATE,
    train_until DATE,
    eval_split_date DATE,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ml_models_strategy ON ml_models (strategy_id, universe_id, created_at DESC);

-- Sector-ETF swing Phase 2: paper positions. Fills are logged by hand (quant-sector-swing-positions);
-- the daily scan only refreshes the tracking columns and flags exit signals, it never sells.
CREATE TABLE IF NOT EXISTS sector_swing_positions (
    id BIGSERIAL PRIMARY KEY,
    ticker VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    source_run_id BIGINT,
    entry_date DATE NOT NULL,
    entry_price DOUBLE PRECISION NOT NULL,
    initial_shares INT NOT NULL,
    open_shares INT NOT NULL,
    initial_stop DOUBLE PRECISION NOT NULL,
    target_price DOUBLE PRECISION NOT NULL,
    trail_mode VARCHAR(16) NOT NULL,
    max_hold_days INT NOT NULL,
    current_stop DOUBLE PRECISION NOT NULL,
    trail_level DOUBLE PRECISION,
    target_reached BOOLEAN NOT NULL DEFAULT FALSE,
    highest_close DOUBLE PRECISION,
    last_close DOUBLE PRECISION,
    last_bar_date DATE,
    bars_held INT NOT NULL DEFAULT 0,
    exit_signal VARCHAR(32),
    exit_signal_date DATE,
    exit_signal_detail TEXT,
    closed_date DATE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sector_swing_positions_status_chk CHECK (status IN ('open', 'closed')),
    CONSTRAINT sector_swing_positions_shares_chk
        CHECK (initial_shares > 0 AND open_shares >= 0 AND open_shares <= initial_shares),
    CONSTRAINT sector_swing_positions_stop_chk CHECK (entry_price > initial_stop)
);

-- At most one open paper position per ETF.
CREATE UNIQUE INDEX IF NOT EXISTS uq_sector_swing_positions_open_ticker
    ON sector_swing_positions (ticker) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_sector_swing_positions_status
    ON sector_swing_positions (status, entry_date DESC);

CREATE TABLE IF NOT EXISTS sector_swing_fills (
    id BIGSERIAL PRIMARY KEY,
    position_id BIGINT NOT NULL REFERENCES sector_swing_positions(id) ON DELETE CASCADE,
    side VARCHAR(4) NOT NULL,
    fill_date DATE NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    shares INT NOT NULL,
    reason VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT sector_swing_fills_side_chk CHECK (side IN ('buy', 'sell')),
    CONSTRAINT sector_swing_fills_values_chk CHECK (price > 0 AND shares > 0)
);

CREATE INDEX IF NOT EXISTS idx_sector_swing_fills_position ON sector_swing_fills (position_id);
CREATE INDEX IF NOT EXISTS idx_sector_swing_fills_date ON sector_swing_fills (side, fill_date);
