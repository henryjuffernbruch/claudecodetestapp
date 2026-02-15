# SPECTER - Autonomous Attention-Trading Intelligence System

A real-time system that measures social engagement across Twitter/X, Reddit, and YouTube to detect attention patterns and generate trading signals for prediction markets.

## Overview

SPECTER (Social Pulse Extraction for Cross-market Trading and Edge Recognition) ingests raw social engagement data, computes a normalized Engagement Index every 60 seconds, classifies attention decay patterns in real-time, and generates trading signals when attention diverges from prediction market pricing.

**Status**: Phase 1 (Data Foundation) - Data ingestion and EI computation working.

## Quick Start

### 1. Setup

```bash
# Clone repository
cd /path/to/specter

# Create virtual environment
python3.11 -m venv specter_env
source specter_env/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure API Credentials

Copy the secrets template and add your credentials:

```bash
cp specter/config/secrets.py.template specter/config/secrets.py
```

Edit `specter/config/secrets.py` and add:
- `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` (from https://www.reddit.com/prefs/apps)
- `YOUTUBE_API_KEY` (from https://console.cloud.google.com)
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (optional, for alerts)

### 3. Run the System

```bash
python -m specter.main
```

The system will:
1. Collect engagement data from Twitter, Reddit, YouTube every 60 seconds
2. Compute Engagement Index for each tracked topic
3. Store all data in `specter/data/specter.db`
4. Log activity to `specter/logs/specter.log` and console

## System Architecture

```
specter/
├── config/           # Configuration & secrets
├── ingestion/        # Data collection (Twitter, Reddit, YouTube)
├── index/            # EI computation pipeline
├── classifier/       # Decay pattern classification (Phase 2)
├── signals/          # Trading signal generation (Phase 2)
├── execution/        # Trade execution (Phase 3)
├── storage/          # Database & logging
├── monitoring/       # Alerts & dashboard (Phase 2-3)
└── main.py          # Main event loop
```

## Configuration

Edit `specter/config/settings.py` to adjust:
- Topics to track (`TRACKED_TOPICS`)
- Poll interval (`POLL_INTERVAL_SECONDS`)
- Index computation parameters (EMA span, decay half-life, etc.)
- Trading settings (Kelly fraction, risk limits, etc.)
- Logging level (`LOG_LEVEL`)

## Tracked Topics (Phase 1)

- **BTC** - Bitcoin (crypto)
- **ETH** - Ethereum (crypto)
- **SOL** - Solana (crypto)
- **TRUMP** - Trump news (politics)
- **AI_HYPE** - AI news (tech)

Additional topics can be added by editing `TRACKED_TOPICS` in `settings.py`.

## Database Schema

Data is stored in SQLite (`specter/data/specter.db`):

- **raw_signals** - Raw engagement metrics from each platform
- **engagement_index** - Computed EI values (0-1 scale)
- **classifications** - Decay pattern classifications (Phase 2)
- **trades** - Trade log with P&L (Phase 3)

## Pipeline Steps (Phase 1)

The EI computation follows the Dollar of Attention (DoA) framework:

1. **Normalize** - Z-score normalization per platform/metric to 0-1 scale
2. **Clip Outliers** - 95th percentile clipping to prevent whale dominance
3. **Time Decay** - Exponential decay weighting (4-hour half-life default)
4. **Deseasonalize** - Remove time-of-day/day-of-week baseline (after 2 weeks)
5. **Smooth** - Exponential Moving Average (5-minute EMA)

Output: **Engagement Index** (0-1 scale) per topic, updated every 60 seconds.

## Phase Roadmap

### Phase 1 ✓ (In Progress)
- [x] Data ingestion (Twitter via snscrape, Reddit, YouTube)
- [x] EI computation pipeline
- [x] Database storage
- [ ] Verify data quality & system stability

### Phase 2 (Signal Generation)
- [ ] Decay pattern classifier (rule-based)
- [ ] Divergence detection (EI vs. price)
- [ ] Trading signal generation
- [ ] Telegram alerts

### Phase 3 (Autonomous Trading)
- [ ] Kalshi API integration
- [ ] Kelly-criterion position sizing
- [ ] Paper trading mode (3-5 day validation)
- [ ] Live trading with safety guards

### Phase 4 (Evolution)
- [ ] ML classifier training
- [ ] Backtesting engine
- [ ] Trendle integration
- [ ] Performance optimization

## Monitoring

Monitor real-time data flow:

```bash
# Watch logs
tail -f specter/logs/specter.log

# Query database
sqlite3 specter/data/specter.db
> SELECT topic, smoothed_ei FROM engagement_index ORDER BY timestamp DESC LIMIT 10;
```

## Troubleshooting

**No data being collected?**
- Check credentials in `specter/config/secrets.py`
- Verify internet connection
- Check logs: `tail -f specter/logs/specter.log`

**Database locked?**
- Stop the system (Ctrl+C)
- Delete `specter/data/specter.db-journal` if it exists
- Restart

**API quota exhausted?**
- YouTube: Resets daily at midnight UTC
- Reddit: 100 req/min (free tier, should not hit)
- Twitter: Rate limited by snscrape

## Performance

- **Memory**: ~50-100 MB (steady state)
- **CPU**: <5% (mostly sleeping between polls)
- **Network**: ~1-2 MB per hour (depends on data volume)
- **Storage**: ~1 MB per day (SQLite)

## Security Notes

- **Never commit secrets.py** - It's in .gitignore
- **Use environment variables** for production credentials
- **Limit API key permissions** - Use read-only API keys
- **Secure the database** - It contains trade history and credentials

## Support

For issues or questions:
1. Check `specter/logs/specter.log` for error details
2. Review the IMPLEMENTATION_PLAN.md
3. Check configuration in `specter/config/settings.py`

## License

Internal use only. Built for Henry's prediction market trading operations.

---

**Next Steps**: Run Phase 1 for 24+ hours to collect baseline data, then implement Phase 2 (classifier + signals).
