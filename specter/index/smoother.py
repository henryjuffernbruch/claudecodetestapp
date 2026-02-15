"""
SPECTER Smoother - Apply exponential moving average (EMA) to smooth noise.
"""

import logging
from datetime import datetime
from typing import Dict, Optional
import numpy as np

from specter.config import settings

logger = logging.getLogger(__name__)


class ExponentialMovingAverage:
    """Exponential Moving Average smoother for engagement index."""

    def __init__(self, span: int = None, alpha: Optional[float] = None):
        """
        Initialize EMA.

        Args:
            span: Number of intervals for EMA (default: 5 minutes)
            alpha: EMA smoothing factor (0-1). If not provided, computed from span.
                   alpha = 2 / (span + 1)
        """
        self.span = span or settings.EMA_SPAN

        # Compute alpha from span if not provided
        # alpha = 2 / (span + 1)
        if alpha is None:
            self.alpha = 2.0 / (self.span + 1.0)
        else:
            self.alpha = alpha

        self.ema_value = None  # Current EMA value
        self.last_raw_value = None
        self.initialized = False

    def update(self, raw_value: float) -> float:
        """
        Update EMA with a new value.

        Formula: EMA_new = alpha * raw_value + (1 - alpha) * EMA_old

        Args:
            raw_value: New raw value (0-1 scale)

        Returns:
            Updated EMA value (0-1 scale)
        """
        # Clamp raw value to [0, 1]
        raw_value = min(1.0, max(0.0, raw_value))
        self.last_raw_value = raw_value

        if not self.initialized:
            # Initialize with first value
            self.ema_value = raw_value
            self.initialized = True
        else:
            # Standard EMA formula
            self.ema_value = self.alpha * raw_value + (1.0 - self.alpha) * self.ema_value

        # Clamp to [0, 1]
        self.ema_value = min(1.0, max(0.0, self.ema_value))

        return self.ema_value

    def get_current(self) -> Optional[float]:
        """Get current EMA value without updating."""
        return self.ema_value

    def reset(self):
        """Reset EMA to uninitialized state."""
        self.ema_value = None
        self.last_raw_value = None
        self.initialized = False

    def get_metadata(self) -> Dict[str, any]:
        """Get smoother metadata."""
        return {
            "span": self.span,
            "alpha": self.alpha,
            "initialized": self.initialized,
            "current_ema": self.ema_value,
            "last_raw": self.last_raw_value,
        }


class Smoother:
    """Manager for smoothing operations per topic."""

    def __init__(self):
        """Initialize smoother manager."""
        self.smoothers = {}  # topic -> EMA instance

    def smooth(self, topic: str, raw_ei: float) -> Dict[str, any]:
        """
        Smooth raw EI value for a topic.

        Args:
            topic: Topic name
            raw_ei: Raw engagement index (0-1 scale)

        Returns:
            {
                "smoothed_ei": float,
                "raw_ei": float,
                "metadata": {...}
            }
        """
        if topic not in self.smoothers:
            self.smoothers[topic] = ExponentialMovingAverage()

        ema = self.smoothers[topic]
        smoothed = ema.update(raw_ei)

        return {
            "smoothed_ei": smoothed,
            "raw_ei": raw_ei,
            "metadata": ema.get_metadata(),
        }

    def get_smoother_for_topic(self, topic: str) -> ExponentialMovingAverage:
        """Get EMA instance for a topic."""
        if topic not in self.smoothers:
            self.smoothers[topic] = ExponentialMovingAverage()
        return self.smoothers[topic]
