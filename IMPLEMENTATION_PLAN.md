# SPECTER Implementation Plan

## Overview
Build an autonomous attention-trading intelligence system that ingests social engagement data, computes engagement indices, classifies attention decay patterns, generates trading signals, and executes trades on Kalshi.

**Timeline:** 4 weeks (split into 4 phases)
**Approach:** Fast demo first (data flowing), then add robustness
**API Strategy:** Use snscrape for Twitter (no direct API needed), Reddit + YouTube direct API
**Trading Mode:** Paper trading first (3-5 days), then live with safety guards

---

## Phase 1: Foundation & Data Flow (Week 1)

**Goal:** Get data ingestion working, compute engagement indices, log everything. No trading yet.

### 1.1 Project Setup
- [ ] Create virtualenv and install dependencies (requests, praw, google-api-python-client, pandas, sqlite-utils, etc.)
- [ ] Set up directory structure (config/, ingestion/, index/, storage/, etc.)
- [ ] Create config/settings.py with all default parameters
- [ ] Create config/secrets.py template (gitignored) for API keys

### 1.2 Storage Layer
- [ ] Create storage/models.py with data classes: RawSignal, EngagementIndex, Classification, TradeSignal
- [ ] Create storage/timeseries_db.py with SQLite schema for: engagement_index, raw_signals, classifications, trades
- [ ] Verify database initialization works (create .db file on first run)

### 1.3 Reddit Ingestion
- [ ] Create ingestion/reddit.py: connect to Reddit API, fetch post/comment counts per topic from configured subreddits
- [ ] Return standardized RawSignal objects
- [ ] Implement error handling and rate limiting (100 req/min free tier)
- [ ] Test: verify you can pull data for BTC, ETH, SOL topics

### 1.4 YouTube Ingestion
- [ ] Create ingestion/youtube.py: connect to YouTube Data API, search for videos per topic
- [ ] Implement quota tracking (10,000 units/day, ~100 per search)
- [ ] Return standardized RawSignal objects
- [ ] Implement backoff if quota approaches limit
- [ ] Test: verify you can pull data for BTC, ETH, SOL topics

### 1.5 Twitter/X Ingestion (Fallback Method)
- [ ] Create ingestion/twitter.py using snscrape library
- [ ] Fetch recent tweets/replies/retweets for topic keywords
- [ ] Return standardized RawSignal objects
- [ ] Implement rate limiting (snscrape is slower but reliable)
- [ ] Test: verify you can pull data for BTC, ETH, SOL topics

### 1.6 Ingestion Aggregator
- [ ] Create ingestion/aggregator.py: orchestrate all three platform collectors
- [ ] Run all three in parallel (async or threading)
- [ ] Combine results into per-topic signal lists
- [ ] Log any platform failures; continue with remaining platforms
- [ ] Return aggregated RawSignal list

### 1.7 Engagement Index Computation Pipeline
- [ ] Create index/normalizer.py: Z-score normalization per platform/metric over 24h rolling window
- [ ] Create index/outlier_clipper.py: 95th percentile clipping per topic per interval
- [ ] Create index/time_decay.py: exponential decay weighting with configurable half-life
- [ ] Create index/deseasonalizer.py: baseline subtraction (stub initially, activate after 2 weeks of data)
- [ ] Create index/smoother.py: exponential moving average (EMA) with configurable span
- [ ] Create index/engine.py: full pipeline orchestration (normalize → clip → decay → deseasonalize → smooth)
- [ ] Test: feed known data through pipeline, verify EI values are sensible (0-1 scale)

### 1.8 Main Loop & Persistence
- [ ] Create main.py with core 60-second loop:
  - Ingest latest data
  - Compute EI for all topics
  - Store results in database
  - Log to stdout
- [ ] Add graceful shutdown handling (Ctrl+C)
- [ ] Verify system runs continuously without crashing
- [ ] Verify database accumulates data correctly

### 1.9 Testing & Validation
- [ ] Run main loop for 1-2 hours, collect data for all 5 topics
- [ ] Spot-check database entries for correctness
- [ ] Verify no duplicate entries on restart
- [ ] Create simple README with setup instructions

**Deliverable:** System runs continuously, ingests data from all three platforms, computes EI every 60 seconds, logs everything to SQLite. No trading yet.

---

## Phase 2: Intelligence & Signals (Week 2)

**Goal:** Detect attention patterns, classify decay archetypes, generate trading signals.

### 2.1 Feature Extraction
- [ ] Create classifier/features.py with rolling window feature computation:
  - first_derivative (rate of change of EI)
  - second_derivative (acceleration of EI)
  - variance_ratio (recent variance / historical variance)
  - peak_distance (intervals since last local max)
  - autocorrelation_lag (dominant periodic pattern)
  - duration_above_baseline (how long EI elevated)
- [ ] Test: verify features are computed correctly on known patterns

### 2.2 Rule-Based Classifier
- [ ] Create classifier/rules.py with classification logic for 4 archetypes:
  - SPIKE_DECAY: sharp spike + consistent negative second derivative
  - PLATEAU_CLIFF: low variance at elevated level + sudden drop
  - SLOW_BUILD: positive first derivative + positive second derivative (convex)
  - OSCILLATION: strong autocorrelation + periodic behavior
- [ ] Output: archetype name + confidence score (0-1)
- [ ] Test: verify classifier on synthetic EI time series (spike, plateau, ramps, oscillations)

### 2.3 Classification Integration
- [ ] Update main.py to run classifier on each topic's EI window
- [ ] Store classifications in database (topic, timestamp, archetype, confidence, features)
- [ ] Add classification to every loop iteration

### 2.4 Divergence Detection
- [ ] Create signals/divergence.py: compute EI change vs. market price change
- [ ] Formula: divergence_pct = (EI_change_pct - price_change_pct) / price_change_pct
- [ ] Flag divergence when magnitude exceeds threshold
- [ ] Test: verify calculation on known EI + price time series

### 2.5 Kalshi Contract Mapper
- [ ] Create signals/kalshi_mapper.py: map topics to Kalshi contract IDs
- [ ] Hardcode mappings: BTC → KXBTC, ETH → KXETH, SOL → KXSOL
- [ ] Add direction logic (positive correlation for all three)
- [ ] Add placeholder for future Trendle mapping

### 2.6 Signal Generator
- [ ] Create signals/generator.py: combine archetype classification + divergence detection
- [ ] Output: TradeSignal objects with topic, venue, direction, confidence, archetype, divergence, reasoning
- [ ] Filter: only emit signals when divergence > threshold (default 15%)
- [ ] Rank by confidence (high confidence = high priority)
- [ ] Test: verify signal generation on synthetic scenarios

### 2.7 Monitoring & Alerts (Telegram)
- [ ] Create monitoring/alerts.py: Telegram bot integration
- [ ] Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in secrets.py
- [ ] Alert types: SIGNAL, SYSTEM_STATUS, ERROR
- [ ] Send alert on every signal detected
- [ ] Test: verify you receive Telegram alerts

### 2.8 Update Main Loop
- [ ] Add signal generation after classification step
- [ ] Add Telegram alerting on signals
- [ ] Run for 24+ hours, verify signals are detected and alerts sent

**Deliverable:** System detects attention patterns, classifies archetypes, generates trading signals, sends Telegram alerts. No execution yet.

---

## Phase 3: Execution & Trading (Week 3)

**Goal:** Execute trades on Kalshi with safety guards and paper trading mode.

### 3.1 Kalshi API Client
- [ ] Create execution/kalshi_client.py with REST API wrapper:
  - get_markets() / get_orderbook(contract_id) for price lookup
  - place_order(contract_id, direction, size, price) for trade entry
  - get_positions() / close_position(position_id) for position management
  - Implement HMAC signature authentication per Kalshi spec
  - Error handling + retry logic for transient failures
- [ ] Test: dry-run a few API calls (no actual trades)

### 3.2 Position Sizing
- [ ] Create execution/position_sizer.py with Kelly criterion:
  - Inputs: bankroll, win probability (from signal confidence), contract odds
  - Output: position size in USD
  - Apply 0.25 fractional Kelly (conservative)
  - Hard cap: never exceed 10% of bankroll per trade
  - Test: verify position sizing makes sense for different confidence levels

### 3.3 Paper Trading Mode
- [ ] Add TRADING_MODE = "paper" | "live" setting
- [ ] In paper mode: log trades to database WITHOUT executing on Kalshi
- [ ] Add execute/executor.py that respects trading mode
- [ ] Implement simulated fills (use current market price)
- [ ] Calculate simulated P&L
- [ ] Run system in paper mode for 3-5 days (collect 20+ paper trades)

### 3.4 Trade Logging
- [ ] Create storage/trade_log.py: log all trades (paper + live) to database
- [ ] Schema: id, topic, venue, direction, entry_price, exit_price, size, pnl, opened_at, closed_at
- [ ] Add entry + exit logging to executor
- [ ] Calculate P&L, win rate, Sharpe ratio

### 3.5 Safety Guards
- [ ] Add daily loss limit: stop trading if daily loss exceeds 20% of bankroll
- [ ] Add position timeout: auto-close any position open > 2 hours
- [ ] Add hard stop-loss per trade (default: 50% loss triggers auto-close)
- [ ] Add Telegram kill switch: "/kill" command stops all trading + closes positions
- [ ] Add heartbeat: system sends "alive" message every hour (or alert if missing)

### 3.6 Dashboard
- [ ] Create monitoring/dashboard.py with real-time info (simple terminal-based using Rich):
  - Current EI per topic + trend
  - Active classifications + confidence
  - Open positions + unrealized P&L
  - Total P&L + win rate
  - System health (last update time, data freshness)
- [ ] Update dashboard every loop iteration

### 3.7 Paper Trading Validation
- [ ] Run system in paper mode for 3-5 days (until 20+ paper trades logged)
- [ ] Review P&L, win rate, Sharpe ratio
- [ ] Spot-check signals: were they reasonable?
- [ ] Tune divergence threshold if signal quality is poor

### 3.8 Go Live
- [ ] Set TRADING_MODE = "live"
- [ ] Start with 0.25 Kelly fractional sizing (conservative)
- [ ] Monitor live trades closely for first 24-48 hours
- [ ] Alert on every execution + close

**Deliverable:** System trades autonomously on Kalshi with safety guards. Paper trading validated first.

---

## Phase 4: Refinement & Evolution (Week 4+)

**Goal:** Improve classifier, add more topics, optimize parameters.

### 4.1 ML Classifier
- [ ] Collect 500+ logged attention curves from Phase 1-3
- [ ] Create classifier/ml_classifier.py: train gradient boosted tree (XGBoost) on logged data
- [ ] Features: same as rule-based + additional (Hurst exponent, spectral density, etc.)
- [ ] Labels: initially from rule-based classifier, manually corrected
- [ ] Retrain weekly on new data
- [ ] A/B test ML classifier vs. rule-based on validation set

### 4.2 Backtesting Engine
- [ ] Create backtest.py: replay historical EI + price data through classifier
- [ ] Validate classifier accuracy: % of archetypes that materialized as predicted
- [ ] Validate trading signals: % profitable, Sharpe ratio, max drawdown
- [ ] Optimize parameters based on backtest results

### 4.3 Additional Topics
- [ ] Monitor Trendle for API access
- [ ] When Trendle API available: implement execution/trendle_client.py
- [ ] Add more topics based on Trendle's listed narratives
- [ ] Expand classifier training data

### 4.4 Parameter Tuning
- [ ] Tune EMA_SPAN, divergence thresholds, Kelly fraction based on live performance
- [ ] Adjust platform weights if one platform correlates better with trading opportunity
- [ ] Modify decay half-life per topic category

### 4.5 System Monitoring
- [ ] Add comprehensive logging (log every step to timestamped files)
- [ ] Create health check endpoints: /status, /positions, /performance
- [ ] Add weekly performance reports to Telegram
- [ ] Monitor data freshness alerts if API goes down

---

## Critical Implementation Notes

### Code Quality (Fast Demo Priority)
- Clean, readable code with clear module boundaries
- Comments on complex logic, especially decay calculation
- No premature abstraction — keep it simple
- Test each module independently as you build

### Error Handling (Degraded Gracefully)
- Each API call has try/except + retry logic
- If one platform fails, continue with others
- Log all errors with context
- Partial data is better than no data

### Data Integrity
- Every datapoint has UTC timestamp
- Idempotent writes (no double-counting on restart)
- Validate all incoming data
- No future-dated entries

### Autonomy Safety
- Paper trading mode mandatory (3-5 days validation)
- Daily loss limit (20% of bankroll)
- Kill switch via Telegram "/kill"
- Heartbeat every hour (or alert)
- Max trade duration 2 hours

---

## Success Metrics (30-Day Goal)

- [ ] Signal accuracy: >55% of signals result in profitable trades
- [ ] Classifier accuracy: >60% of decay classifications match actual subsequent curve shape
- [ ] P&L: Positive net profit after fees
- [ ] Sharpe ratio: >1.0
- [ ] System uptime: >95% (data collection + trading active)
- [ ] Win rate: >55%

---

## Build Order (Recommended Sequence)

1. Phase 1.1 - 1.2: Setup + Storage
2. Phase 1.3 - 1.5: Ingestion for all 3 platforms
3. Phase 1.6 - 1.7: Aggregator + Index Engine
4. Phase 1.8 - 1.9: Main loop + validation
5. Phase 2.1 - 2.8: Classifier + Signals + Alerts
6. Phase 3.1 - 3.8: Execution + Paper trading + Live trading
7. Phase 4: ML + Backtesting + Refinement

---

## Files to Create (Phase 1)

```
specter/
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── topics.py
│   └── secrets.py (gitignored)
├── ingestion/
│   ├── __init__.py
│   ├── twitter.py
│   ├── reddit.py
│   ├── youtube.py
│   └── aggregator.py
├── index/
│   ├── __init__.py
│   ├── normalizer.py
│   ├── outlier_clipper.py
│   ├── time_decay.py
│   ├── deseasonalizer.py
│   ├── smoother.py
│   └── engine.py
├── classifier/
│   ├── __init__.py
│   ├── features.py
│   ├── rules.py
│   └── archetypes.py
├── signals/
│   ├── __init__.py
│   ├── divergence.py
│   ├── kalshi_mapper.py
│   └── generator.py
├── execution/
│   ├── __init__.py
│   ├── kalshi_client.py
│   ├── position_sizer.py
│   └── executor.py
├── storage/
│   ├── __init__.py
│   ├── models.py
│   ├── timeseries_db.py
│   └── trade_log.py
├── monitoring/
│   ├── __init__.py
│   ├── alerts.py
│   └── dashboard.py
├── main.py
├── backtest.py
├── requirements.txt
└── README.md
```

---

## Next Steps

1. ✓ Approve this plan
2. Create project structure + install dependencies (Phase 1.1)
3. Implement storage layer (Phase 1.2)
4. Build data ingestion (Phase 1.3 - 1.5)
5. Continue phase by phase

