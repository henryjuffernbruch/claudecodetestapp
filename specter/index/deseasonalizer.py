"""
SPECTER Deseasonalizer - Remove recurring baseline patterns (time-of-day, day-of-week effects).
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import numpy as np

from specter.config import settings

logger = logging.getLogger(__name__)


class Deseasonalizer:
    """
    Deseasonalizes engagement index by removing recurring baseline patterns.
    Accounts for time-of-day and day-of-week effects.
    """

    def __init__(self, enabled: bool = None, window_days: int = None):
        """
        Initialize deseasonalizer.

        Args:
            enabled: Whether deseasonalization is enabled (requires 2+ weeks of data)
            window_days: How many days of history to use for baseline (default: 14)
        """
        self.enabled = enabled if enabled is not None else settings.DESEASONALIZE_ENABLED
        self.window_days = window_days or settings.DESEASONALIZE_WINDOW_DAYS
        self.baseline_cache = {}  # Cache for baseline values

    def _get_hour_of_day(self, dt: datetime) -> int:
        """Get hour of day (0-23)."""
        return dt.hour

    def _get_day_of_week(self, dt: datetime) -> int:
        """Get day of week (0=Monday, 6=Sunday)."""
        return dt.weekday()

    def _get_key(self, hour_of_day: int, day_of_week: int) -> str:
        """Create cache key for baseline."""
        return f"h{hour_of_day:02d}_d{day_of_week}"

    def update_baseline(
        self,
        ei_value: float,
        timestamp: datetime
    ):
        """Update baseline statistics for a given time period."""
        if not self.enabled:
            return

        hour = self._get_hour_of_day(timestamp)
        day = self._get_day_of_week(timestamp)
        key = self._get_key(hour, day)

        if key not in self.baseline_cache:
            self.baseline_cache[key] = []

        self.baseline_cache[key].append(ei_value)

        # Keep only recent history
        max_samples = self.window_days * 24  # One value per hour
        if len(self.baseline_cache[key]) > max_samples:
            self.baseline_cache[key] = self.baseline_cache[key][-max_samples:]

    def get_baseline(
        self,
        timestamp: datetime
    ) -> Optional[Tuple[float, float]]:
        """
        Get baseline (mean, std) for a given time period.

        Returns:
            (mean, std) if sufficient data, None otherwise
        """
        if not self.enabled:
            return None

        hour = self._get_hour_of_day(timestamp)
        day = self._get_day_of_week(timestamp)
        key = self._get_key(hour, day)

        if key not in self.baseline_cache or len(self.baseline_cache[key]) < 3:
            return None  # Need at least 3 samples

        values = np.array(self.baseline_cache[key])
        mean = float(np.mean(values))
        std = float(np.std(values))

        return (mean, std)

    def deseasonalize(
        self,
        ei_value: float,
        timestamp: datetime
    ) -> Dict[str, any]:
        """
        Remove seasonal component from EI value.

        Returns:
            {
                "deseasonalized_ei": float,  # ei_value - baseline_mean
                "baseline_mean": Optional[float],
                "baseline_std": Optional[float],
                "metadata": {...}
            }
        """
        baseline = self.get_baseline(timestamp)

        if baseline is None:
            # Not enough data yet, return raw value
            return {
                "deseasonalized_ei": ei_value,
                "baseline_mean": None,
                "baseline_std": None,
                "metadata": {
                    "deseasonalization_applied": False,
                    "reason": "insufficient_data",
                },
            }

        baseline_mean, baseline_std = baseline

        # Deseasonalize: subtract baseline
        deseasonalized = ei_value - baseline_mean

        # Clamp (can go negative)
        deseasonalized = max(-1.0, min(1.0, deseasonalized))

        return {
            "deseasonalized_ei": deseasonalized,
            "baseline_mean": baseline_mean,
            "baseline_std": baseline_std,
            "metadata": {
                "deseasonalization_applied": True,
                "hour_of_day": self._get_hour_of_day(timestamp),
                "day_of_week": self._get_day_of_week(timestamp),
            },
        }
