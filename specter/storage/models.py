"""
SPECTER Data Models - Dataclasses for all system objects.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional, List
import json


@dataclass
class RawSignal:
    """Raw engagement signal from a single platform."""
    topic: str
    platform: str  # "twitter", "reddit", "youtube"
    timestamp: datetime
    metrics: Dict[str, any]  # platform-specific raw counts

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class EngagementIndex:
    """Computed engagement index for a topic at a specific time."""
    topic: str
    timestamp: datetime
    raw_ei: float  # before smoothing
    smoothed_ei: float  # final value (0-1 scale)
    components: Dict[str, float]  # per-platform breakdown
    metadata: Dict[str, any]  # decay params, clip stats, etc.

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class Classification:
    """Decay pattern classification for a topic."""
    topic: str
    timestamp: datetime
    archetype: str  # "SPIKE_DECAY", "PLATEAU_CLIFF", "SLOW_BUILD", "OSCILLATION"
    confidence: float  # 0-1
    features: Dict[str, float]  # first_derivative, second_derivative, etc.
    metadata: Dict[str, any]  # additional context

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class TradeSignal:
    """Generated trading signal."""
    topic: str
    venue: str  # "kalshi", "trendle"
    direction: str  # "long", "short"
    confidence: float  # 0-1
    archetype: str  # decay classification
    divergence: float  # magnitude of divergence (%)
    entry_price: float  # current contract/index price
    timestamp: datetime
    reasoning: str  # human-readable explanation

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


@dataclass
class Trade:
    """Logged trade (paper or live)."""
    id: Optional[str]  # auto-generated
    topic: str
    venue: str  # "kalshi"
    direction: str  # "long", "short"
    entry_price: float
    entry_size: float  # USD amount or shares
    exit_price: Optional[float]
    exit_size: Optional[float]
    pnl: Optional[float]  # profit/loss
    signal_confidence: float
    signal_archetype: str
    opened_at: datetime
    closed_at: Optional[datetime]
    status: str  # "open", "closed", "cancelled"
    notes: Optional[str]

    def to_dict(self):
        d = asdict(self)
        d["opened_at"] = self.opened_at.isoformat()
        if self.closed_at:
            d["closed_at"] = self.closed_at.isoformat()
        return d


@dataclass
class SystemStatus:
    """System health and performance metrics."""
    timestamp: datetime
    is_running: bool
    last_data_update: datetime
    data_freshness_seconds: Optional[int]
    active_position_count: int
    total_pnl: float
    daily_pnl: float
    daily_loss_pct: float
    signal_count_today: int
    uptime_hours: float
    errors_last_hour: List[str]

    def to_dict(self):
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["last_data_update"] = self.last_data_update.isoformat()
        return d


# ============================================================================
# Archetype Definitions
# ============================================================================

ARCHETYPE_SPIKE_DECAY = "SPIKE_DECAY"
ARCHETYPE_PLATEAU_CLIFF = "PLATEAU_CLIFF"
ARCHETYPE_SLOW_BUILD = "SLOW_BUILD"
ARCHETYPE_OSCILLATION = "OSCILLATION"
ARCHETYPE_UNKNOWN = "UNKNOWN"

ARCHETYPES = [
    ARCHETYPE_SPIKE_DECAY,
    ARCHETYPE_PLATEAU_CLIFF,
    ARCHETYPE_SLOW_BUILD,
    ARCHETYPE_OSCILLATION,
    ARCHETYPE_UNKNOWN,
]
