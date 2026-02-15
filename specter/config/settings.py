"""
SPECTER Configuration - All default parameters and system-wide settings.
"""

import os
from datetime import datetime, timedelta

# ============================================================================
# TIMING
# ============================================================================
POLL_INTERVAL_SECONDS = 60
EI_WINDOW_SIZE = 1440  # 24 hours of 1-minute intervals

# ============================================================================
# DATABASE
# ============================================================================
DB_PATH = os.getenv("SPECTER_DB_PATH", "specter/data/specter.db")
DB_ENSURE_DIR = True

# ============================================================================
# PLATFORM INGESTION SETTINGS
# ============================================================================

# Twitter/X (via snscrape)
TWITTER_ENABLED = True
TWITTER_RATE_LIMIT_REQUESTS_PER_MIN = 30  # conservative for snscrape
TWITTER_RETRIES = 3
TWITTER_RETRY_BACKOFF_SECONDS = 5

# Reddit
REDDIT_ENABLED = True
REDDIT_RATE_LIMIT_REQUESTS_PER_MIN = 100  # free tier limit
REDDIT_RETRIES = 3
REDDIT_RETRY_BACKOFF_SECONDS = 5

# YouTube
YOUTUBE_ENABLED = True
YOUTUBE_QUOTA_PER_DAY = 10000
YOUTUBE_COST_PER_SEARCH = 100
YOUTUBE_MAX_SEARCHES_PER_DAY = 50  # conservative budget
YOUTUBE_RETRIES = 3
YOUTUBE_RETRY_BACKOFF_SECONDS = 5

# ============================================================================
# ENGAGEMENT INDEX COMPUTATION
# ============================================================================

# Normalization
PLATFORM_WEIGHTS = {
    "twitter": 0.40,
    "reddit": 0.35,
    "youtube": 0.25,
}
ZSCORE_WINDOW_HOURS = 24  # 24h rolling window for Z-score normalization
ZSCORE_WINDOW_INTERVALS = 1440  # number of 1-min intervals in 24h

# Outlier Clipping
CLIP_PERCENTILE = 95

# Time Decay
DECAY_HALF_LIFE_HOURS = 4.0  # Default for crypto topics
DECAY_HALF_LIFE_HOURS_SPORTS = 12.0
DECAY_HALF_LIFE_HOURS_POLITICS = 24.0

# Smoothing (EMA)
EMA_SPAN = 5  # 5-minute exponential moving average

# Deseasonalization
DESEASONALIZE_ENABLED = False  # Enable after 2 weeks of data
DESEASONALIZE_WINDOW_DAYS = 14

# ============================================================================
# CLASSIFIER SETTINGS
# ============================================================================

# Rule-based classifier window
CLASSIFIER_WINDOW_INTERVALS = 30  # 30 minutes of EI data

# Spike-Decay detection
SPIKE_DECAY_FIRST_DERIV_THRESHOLD = 1.5  # std devs
SPIKE_DECAY_SECOND_DERIV_THRESHOLD = -1.0
SPIKE_DECAY_CONSISTENCY_INTERVALS = 3

# Plateau detection
PLATEAU_VARIANCE_RATIO_THRESHOLD = 0.3
PLATEAU_MIN_DURATION_INTERVALS = 15
PLATEAU_CLIFF_FIRST_DERIV_THRESHOLD = -2.0  # std devs

# Slow Build detection
SLOW_BUILD_MIN_POSITIVE_INTERVALS = 10
SLOW_BUILD_MAX_BASELINE_MULTIPLE = 1.5

# Oscillation detection
OSCILLATION_AUTOCORR_THRESHOLD = 0.6
OSCILLATION_LAG_MIN = 10
OSCILLATION_LAG_MAX = 100

# ============================================================================
# SIGNAL GENERATION
# ============================================================================

# Divergence Detection
DIVERGENCE_ENTRY_THRESHOLD = 0.15  # 15% divergence to trigger
DIVERGENCE_STRONG_THRESHOLD = 0.25  # 25% for high-confidence
DIVERGENCE_EXIT_THRESHOLD = 0.05  # 5% convergence to exit

# ============================================================================
# EXECUTION & TRADING
# ============================================================================

# Trading Mode
TRADING_MODE = os.getenv("TRADING_MODE", "paper")  # "paper" or "live"

# Position Sizing (Kelly Criterion)
KELLY_FRACTION = 0.25  # Quarter Kelly (conservative)
INITIAL_BANKROLL = float(os.getenv("INITIAL_BANKROLL", "43.0"))  # USD

# Risk Management
MAX_RISK_PER_TRADE = 0.10  # 10% of bankroll per trade
DAILY_LOSS_LIMIT_PCT = 0.20  # 20% max daily loss
POSITION_TIMEOUT_MINUTES = 120  # Auto-close positions after 2 hours
HARD_STOPLOSS_PCT = 0.50  # Auto-close if trade loses 50%

# Kalshi API
KALSHI_API_BASE_URL = os.getenv("KALSHI_API_BASE_URL", "https://api.kalshi.com/exchange/v2")
KALSHI_RETRIES = 3
KALSHI_RETRY_BACKOFF_SECONDS = 5

# Trendle API (future)
TRENDLE_API_BASE_URL = os.getenv("TRENDLE_API_BASE_URL", "")
TRENDLE_ENABLED = False

# ============================================================================
# MONITORING & ALERTS
# ============================================================================

# Telegram
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Heartbeat
HEARTBEAT_ENABLED = True
HEARTBEAT_INTERVAL_SECONDS = 3600  # 1 hour

# Dashboard
DASHBOARD_UPDATE_INTERVAL_SECONDS = 10

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = "specter/logs"
LOG_ENSURE_DIR = True

# ============================================================================
# TOPICS TO TRACK
# ============================================================================

TRACKED_TOPICS = {
    "BTC": {
        "keywords_twitter": ["bitcoin", "btc", "#bitcoin"],
        "subreddits": ["r/bitcoin", "r/cryptocurrency"],
        "youtube_search": "bitcoin",
        "category": "crypto",
        "decay_half_life_hours": 4.0,
    },
    "ETH": {
        "keywords_twitter": ["ethereum", "eth", "#ethereum"],
        "subreddits": ["r/ethereum", "r/cryptocurrency"],
        "youtube_search": "ethereum",
        "category": "crypto",
        "decay_half_life_hours": 4.0,
    },
    "SOL": {
        "keywords_twitter": ["solana", "sol", "#solana"],
        "subreddits": ["r/solana", "r/cryptocurrency"],
        "youtube_search": "solana",
        "category": "crypto",
        "decay_half_life_hours": 4.0,
    },
    "TRUMP": {
        "keywords_twitter": ["trump", "#trump", "potus"],
        "subreddits": ["r/politics", "r/news"],
        "youtube_search": "trump news",
        "category": "politics",
        "decay_half_life_hours": 24.0,
    },
    "AI_HYPE": {
        "keywords_twitter": ["artificial intelligence", "chatgpt", "openai", "claude"],
        "subreddits": ["r/artificial", "r/machinelearning"],
        "youtube_search": "AI news",
        "category": "tech",
        "decay_half_life_hours": 12.0,
    },
}

# ============================================================================
# HELPER: Get decay half-life for topic
# ============================================================================

def get_decay_half_life(topic: str) -> float:
    """Get decay half-life for a specific topic."""
    if topic in TRACKED_TOPICS:
        return TRACKED_TOPICS[topic].get("decay_half_life_hours", DECAY_HALF_LIFE_HOURS)
    return DECAY_HALF_LIFE_HOURS
