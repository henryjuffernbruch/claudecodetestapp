"""
SPECTER Time Decay - Apply exponential decay to historical engagement values.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import numpy as np

from specter.config import settings

logger = logging.getLogger(__name__)


class TimeDecayProcessor:
    """Applies exponential time decay to engagement index values."""

    def __init__(self, half_life_hours: float = None):
        """
        Initialize decay processor.

        Args:
            half_life_hours: Time for value to decay to 50% (default: 4 hours for crypto)
        """
        self.half_life_hours = half_life_hours or settings.DECAY_HALF_LIFE_HOURS
        # Compute decay constant: lambda = ln(2) / half_life
        self.lambda_param = np.log(2) / self.half_life_hours

    def compute_decay_weight(
        self,
        current_time: datetime,
        value_time: datetime
    ) -> float:
        """
        Compute decay weight for a value at value_time observed from current_time.

        Formula: weight(t) = exp(-lambda * (now - t))

        Args:
            current_time: Current time (usually now)
            value_time: When the value was recorded

        Returns:
            Weight between 0 and 1
        """
        if value_time > current_time:
            return 0.0  # Future values get 0 weight

        time_diff = (current_time - value_time).total_seconds()
        time_diff_hours = time_diff / 3600.0

        weight = np.exp(-self.lambda_param * time_diff_hours)

        # Clamp to [0, 1]
        weight = min(1.0, max(0.0, weight))

        return weight

    def apply_decay(
        self,
        current_ei: float,
        current_time: datetime,
        historical_eis: List[Tuple[float, datetime]],
        window_hours: int = 24
    ) -> Dict[str, any]:
        """
        Apply exponential decay to compute decayed EI.

        Args:
            current_ei: Most recent EI value
            current_time: Current time
            historical_eis: List of (ei_value, timestamp) tuples (oldest to newest)
            window_hours: How far back to include (default: 24h)

        Returns:
            {
                "decayed_ei": float,
                "decay_weights": [...],
                "effective_values": [...],
                "metadata": {...}
            }
        """
        if not historical_eis:
            return {
                "decayed_ei": current_ei,
                "decay_weights": [1.0],
                "effective_values": [current_ei],
                "metadata": {"data_points": 1},
            }

        # Include current EI as most recent point
        all_eis = list(historical_eis) + [(current_ei, current_time)]

        # Filter to window
        cutoff_time = current_time - timedelta(hours=window_hours)
        filtered_eis = [(ei, ts) for ei, ts in all_eis if ts >= cutoff_time]

        if not filtered_eis:
            filtered_eis = [(current_ei, current_time)]

        # Compute weights
        decay_weights = []
        for ei_value, ei_time in filtered_eis:
            weight = self.compute_decay_weight(current_time, ei_time)
            decay_weights.append(weight)

        # Normalize weights to sum to 1
        total_weight = sum(decay_weights)
        if total_weight > 0:
            normalized_weights = [w / total_weight for w in decay_weights]
        else:
            normalized_weights = [1.0 / len(decay_weights)] * len(decay_weights)

        # Compute weighted average
        ei_values = [ei for ei, _ in filtered_eis]
        decayed_ei = sum(ei * w for ei, w in zip(ei_values, normalized_weights))

        # Clamp to [0, 1]
        decayed_ei = min(1.0, max(0.0, decayed_ei))

        return {
            "decayed_ei": decayed_ei,
            "decay_weights": decay_weights,
            "effective_values": ei_values,
            "metadata": {
                "data_points": len(filtered_eis),
                "half_life_hours": self.half_life_hours,
                "window_hours": window_hours,
                "sum_weights": sum(decay_weights),
            },
        }
