"""
SPECTER Archetype Definitions - Decay pattern archetypes and their characteristics.
"""

from dataclasses import dataclass
from typing import Dict, Optional

# ============================================================================
# Archetype Enumeration
# ============================================================================

ARCHETYPE_SPIKE_DECAY = "SPIKE_DECAY"
ARCHETYPE_PLATEAU_CLIFF = "PLATEAU_CLIFF"
ARCHETYPE_SLOW_BUILD = "SLOW_BUILD"
ARCHETYPE_OSCILLATION = "OSCILLATION"
ARCHETYPE_UNKNOWN = "UNKNOWN"

ALL_ARCHETYPES = [
    ARCHETYPE_SPIKE_DECAY,
    ARCHETYPE_PLATEAU_CLIFF,
    ARCHETYPE_SLOW_BUILD,
    ARCHETYPE_OSCILLATION,
    ARCHETYPE_UNKNOWN,
]

# ============================================================================
# Archetype Descriptions
# ============================================================================

ARCHETYPE_INFO = {
    ARCHETYPE_SPIKE_DECAY: {
        "name": "Spike-and-Decay",
        "description": "Sharp impulse followed by exponential or power-law decay",
        "causes": ["Breaking news", "Viral moments", "Most crypto narratives"],
        "signal_characteristics": [
            "Rapid first derivative spike",
            "Monotonic negative second derivative after peak",
        ],
        "trade_strategy": "Short after peak confirmation (when 2nd deriv turns negative and stays negative)",
        "frequency": "~60% of events",
        "latency": "Low (5-10 min)",
    },
    ARCHETYPE_PLATEAU_CLIFF: {
        "name": "Plateau-and-Cliff",
        "description": "Sustained elevated attention, then sudden collapse",
        "causes": [
            "Institutional/media-sustained narratives",
            "Regulatory hearings",
            "Planned events",
            "Coordinated campaigns",
        ],
        "signal_characteristics": [
            "Low variance at elevated level for extended period",
            "Sharp negative first derivative (cliff)",
        ],
        "trade_strategy": "Short when sustaining force withdraws (variance increase at plateau as leading indicator)",
        "frequency": "~15% of events",
        "latency": "Medium (20-30 min)",
    },
    ARCHETYPE_SLOW_BUILD: {
        "name": "Slow-Build-to-Peak",
        "description": "Low, rising engagement that accelerates as it crosses awareness thresholds",
        "causes": [
            "Genuine grassroots narrative shifts",
            "Organic community growth",
        ],
        "signal_characteristics": [
            "Positive first derivative",
            "Increasing second derivative (convex acceleration)",
            "Sustained below 1.5x baseline",
        ],
        "trade_strategy": "Long early when convex acceleration detected, exit at peak (when 2nd deriv turns negative)",
        "frequency": "~10% of events",
        "latency": "Low (high alpha if caught early)",
    },
    ARCHETYPE_OSCILLATION: {
        "name": "Oscillation",
        "description": "Recurring pulse pattern, never fully dies",
        "causes": [
            "Cyclical narratives",
            "Election cycles",
            "Seasonal events",
            "Recurring crypto themes (ETF specs, halving)",
        ],
        "signal_characteristics": [
            "Quasi-periodic pattern (autocorrelation > 0.6)",
            "Returns to baseline regularly",
        ],
        "trade_strategy": "Mean-revert at extremes of oscillation band",
        "frequency": "~15% of events",
        "latency": "Medium (depend on period)",
    },
    ARCHETYPE_UNKNOWN: {
        "name": "Unknown",
        "description": "No clear pattern detected",
        "causes": ["Insufficient data", "Novel patterns"],
        "signal_characteristics": ["No clear signals"],
        "trade_strategy": "Wait for pattern clarity",
        "frequency": "Rare",
        "latency": "N/A",
    },
}

# ============================================================================
# Archetype Metadata
# ============================================================================

def get_archetype_info(archetype: str) -> Dict:
    """Get information about an archetype."""
    return ARCHETYPE_INFO.get(archetype, ARCHETYPE_INFO[ARCHETYPE_UNKNOWN])


def get_archetype_display_name(archetype: str) -> str:
    """Get human-readable name for archetype."""
    return ARCHETYPE_INFO.get(archetype, {}).get("name", archetype)


def get_trade_strategy(archetype: str) -> str:
    """Get recommended trade strategy for archetype."""
    return ARCHETYPE_INFO.get(archetype, {}).get("trade_strategy", "Wait")


# ============================================================================
# Feature Extraction Targets
# ============================================================================

CLASSIFICATION_FEATURES = [
    "first_derivative",         # Rate of change of EI
    "second_derivative",        # Acceleration of EI
    "variance_ratio",           # Recent variance / historical variance
    "peak_distance",            # Intervals since last local max
    "autocorrelation_lag1",     # First-lag autocorrelation
    "autocorrelation_lag24",    # 24-lag (daily) autocorrelation
    "duration_above_baseline",  # How long EI elevated above 1-std baseline
    "magnitude",                # Current EI - baseline
    "volatility_trend",         # Is volatility increasing or decreasing
]
