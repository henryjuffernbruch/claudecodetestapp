"""
SPECTER Divergence Detection - Detect when EI diverges from market prices.
The primary alpha signal: when attention moves faster than pricing adjusts.
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from collections import deque

from specter.config import settings

logger = logging.getLogger(__name__)


class DivergenceDetector:
    """Detects attention-vs-price divergences."""

    def __init__(self):
        """Initialize divergence detector."""
        self.ei_history = {}  # topic -> deque of (ei, timestamp)
        self.price_history = {}  # topic -> deque of (price, timestamp)
        self.max_history = 60  # Keep last 60 intervals for divergence detection

    def update_ei(self, topic: str, ei_value: float, timestamp: datetime):
        """Update EI value for a topic."""
        if topic not in self.ei_history:
            self.ei_history[topic] = deque(maxlen=self.max_history)

        self.ei_history[topic].append((ei_value, timestamp))

    def update_price(self, topic: str, price: float, timestamp: datetime):
        """Update contract price for a topic."""
        if topic not in self.price_history:
            self.price_history[topic] = deque(maxlen=self.max_history)

        self.price_history[topic].append((price, timestamp))

    def compute_change_rate(
        self,
        history: deque,
        window_intervals: int = 10
    ) -> Optional[float]:
        """
        Compute percentage change rate over a window.

        Args:
            history: Deque of (value, timestamp) tuples
            window_intervals: Number of intervals to look back

        Returns:
            Percentage change (positive or negative), or None if insufficient data
        """
        if len(history) < window_intervals + 1:
            return None

        # Get values from window_intervals ago to now
        old_value = history[-window_intervals-1][0]
        new_value = history[-1][0]

        if old_value < 1e-6:
            return None

        change_pct = (new_value - old_value) / old_value * 100.0
        return change_pct

    def compute_divergence(
        self,
        topic: str,
        window_intervals: int = 10
    ) -> Optional[Dict[str, float]]:
        """
        Compute divergence between EI and price changes.

        Formula: divergence = EI_change_pct - price_change_pct

        Args:
            topic: Topic name
            window_intervals: Number of intervals to analyze (default: 10)

        Returns:
            {
                "divergence_pct": float,  # EI_change - price_change
                "ei_change_pct": float,
                "price_change_pct": float,
                "has_sufficient_data": bool,
            }
            or None if insufficient data
        """
        # Get EI change
        ei_change = self.compute_change_rate(
            self.ei_history.get(topic, deque()),
            window_intervals
        )

        # Get price change
        price_change = self.compute_change_rate(
            self.price_history.get(topic, deque()),
            window_intervals
        )

        if ei_change is None or price_change is None:
            return None

        # Compute divergence
        divergence = ei_change - price_change

        return {
            "divergence_pct": divergence,
            "ei_change_pct": ei_change,
            "price_change_pct": price_change,
            "has_sufficient_data": True,
        }

    def detect_entry_signal(
        self,
        topic: str,
        window_intervals: int = 10
    ) -> Optional[str]:
        """
        Detect if there's an entry signal based on divergence.

        Returns:
            "long" if EI rising faster than price
            "short" if EI falling faster than price (or rising slower)
            None if no clear signal
        """
        div_result = self.compute_divergence(topic, window_intervals)

        if div_result is None:
            return None

        divergence = div_result["divergence_pct"]
        ei_change = div_result["ei_change_pct"]
        price_change = div_result["price_change_pct"]

        # Entry rules:
        # - LONG: EI rising significantly faster than price (positive divergence)
        # - SHORT: EI falling faster than price (negative divergence), or price rising while EI flat/down

        if divergence > settings.DIVERGENCE_ENTRY_THRESHOLD:
            # EI outpacing price to upside = expect price to follow = LONG
            return "long"
        elif divergence < -settings.DIVERGENCE_ENTRY_THRESHOLD:
            # EI underperforming price to upside (or falling when price up) = EXPECT REVERSAL = SHORT
            return "short"

        return None

    def is_strong_signal(
        self,
        topic: str,
        window_intervals: int = 10
    ) -> bool:
        """Check if divergence is strong (> 25% threshold)."""
        div_result = self.compute_divergence(topic, window_intervals)

        if div_result is None:
            return False

        return abs(div_result["divergence_pct"]) > settings.DIVERGENCE_STRONG_THRESHOLD

    def should_exit(
        self,
        topic: str,
        window_intervals: int = 10
    ) -> bool:
        """Check if divergence has converged (signal should be closed)."""
        div_result = self.compute_divergence(topic, window_intervals)

        if div_result is None:
            return False

        # Exit when divergence shrinks below 5%
        return abs(div_result["divergence_pct"]) < settings.DIVERGENCE_EXIT_THRESHOLD

    def get_diagnostics(self, topic: str) -> Dict:
        """Get diagnostic info about a topic's divergence."""
        ei_history = self.ei_history.get(topic, deque())
        price_history = self.price_history.get(topic, deque())

        ei_current = ei_history[-1][0] if ei_history else None
        price_current = price_history[-1][0] if price_history else None

        ei_change_10 = self.compute_change_rate(ei_history, 10)
        price_change_10 = self.compute_change_rate(price_history, 10)

        return {
            "topic": topic,
            "ei_current": ei_current,
            "price_current": price_current,
            "ei_history_length": len(ei_history),
            "price_history_length": len(price_history),
            "ei_change_10": ei_change_10,
            "price_change_10": price_change_10,
            "divergence_10": (ei_change_10 - price_change_10) if (ei_change_10 and price_change_10) else None,
        }
