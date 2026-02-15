"""
SPECTER Index Normalization - Normalize raw engagement metrics to 0-1 scale.
"""

import logging
from typing import Dict, List
from datetime import datetime

import numpy as np
import pandas as pd

from specter.config import settings

logger = logging.getLogger(__name__)


class Normalizer:
    """Normalizes raw engagement metrics across platforms to 0-1 scale."""

    def __init__(self):
        """Initialize normalizer."""
        self.platform_windows = {}  # Store rolling stats per platform

    def _get_platform_metrics(self, platform: str) -> List[str]:
        """Get metric names for a platform."""
        if platform == "twitter":
            return ["tweet_count", "reply_count", "retweet_count", "like_count"]
        elif platform == "reddit":
            return ["posts_count", "comments_count", "avg_upvote_ratio", "top_post_score"]
        elif platform == "youtube":
            return ["video_count", "total_views", "total_comments", "avg_likes"]
        return []

    def _compute_zscore(self, value: float, mean: float, std: float) -> float:
        """Compute Z-score for a value."""
        if std < 1e-6:  # Avoid division by zero
            return 0.0
        return (value - mean) / std

    def _sigmoid(self, z: float, midpoint: float = 0.0, scale: float = 1.0) -> float:
        """Convert Z-score to probability via sigmoid."""
        # sigmoid(z) = 1 / (1 + e^(-z))
        # Scaled version: midpoint + scale * sigmoid(z)
        try:
            return 1.0 / (1.0 + np.exp(-z))
        except (OverflowError, ValueError):
            # Handle extreme values
            return 1.0 if z > 0 else 0.0

    def update_rolling_stats(
        self,
        platform: str,
        metric: str,
        value: float,
        window_size: int = None
    ):
        """Update rolling statistics for a metric."""
        if window_size is None:
            window_size = settings.ZSCORE_WINDOW_INTERVALS

        key = f"{platform}_{metric}"
        if key not in self.platform_windows:
            self.platform_windows[key] = []

        self.platform_windows[key].append(value)

        # Keep only last N values
        if len(self.platform_windows[key]) > window_size:
            self.platform_windows[key] = self.platform_windows[key][-window_size:]

    def get_rolling_stats(self, platform: str, metric: str) -> Dict[str, float]:
        """Get rolling mean and std for a metric."""
        key = f"{platform}_{metric}"
        if key not in self.platform_windows or not self.platform_windows[key]:
            return {"mean": 0.0, "std": 1.0}

        values = np.array(self.platform_windows[key])
        return {
            "mean": float(np.mean(values)),
            "std": float(np.std(values)),
        }

    def normalize_metric(
        self,
        platform: str,
        metric: str,
        value: float
    ) -> float:
        """Normalize a single metric to 0-1 scale using Z-score + sigmoid."""
        # Get rolling stats
        stats = self.get_rolling_stats(platform, metric)
        mean = stats["mean"]
        std = stats["std"]

        # Handle edge cases
        if value < 0:
            value = 0.0

        # Compute Z-score
        z_score = self._compute_zscore(value, mean, std)

        # Convert to 0-1 via sigmoid
        normalized = self._sigmoid(z_score)

        # Clamp to [0, 1]
        normalized = min(1.0, max(0.0, normalized))

        return normalized

    def normalize_platform_signals(
        self,
        platform: str,
        metrics: Dict[str, float]
    ) -> Dict[str, float]:
        """Normalize all metrics for a platform."""
        normalized = {}

        for metric_name, metric_value in metrics.items():
            # Update rolling window
            self.update_rolling_stats(platform, metric_name, metric_value)

            # Normalize
            normalized[metric_name] = self.normalize_metric(
                platform,
                metric_name,
                metric_value
            )

        return normalized

    def compute_platform_ei(
        self,
        platform: str,
        normalized_metrics: Dict[str, float]
    ) -> float:
        """Compute platform-level EI from normalized metrics."""
        if not normalized_metrics:
            return 0.0

        # Simple average of normalized metrics
        values = list(normalized_metrics.values())
        return float(np.mean(values))


class EngagementIndexNormalizer:
    """Full normalization pipeline for raw signals to platform EI values."""

    def __init__(self):
        """Initialize normalizer."""
        self.metric_normalizer = Normalizer()

    def normalize(
        self,
        platform: str,
        metrics: Dict[str, float]
    ) -> Dict[str, any]:
        """
        Normalize raw metrics from a platform.

        Returns:
            {
                "normalized_metrics": {...},  # normalized 0-1 per metric
                "platform_ei": float,         # 0-1 platform-level EI
                "metadata": {...}             # debug info
            }
        """
        # Normalize all metrics
        normalized_metrics = self.metric_normalizer.normalize_platform_signals(
            platform,
            metrics
        )

        # Compute platform-level EI
        platform_ei = self.metric_normalizer.compute_platform_ei(
            platform,
            normalized_metrics
        )

        return {
            "normalized_metrics": normalized_metrics,
            "platform_ei": platform_ei,
            "metadata": {
                "metric_count": len(metrics),
                "platform": platform,
            },
        }
