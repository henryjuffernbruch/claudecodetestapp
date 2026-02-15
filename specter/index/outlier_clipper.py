"""
SPECTER Outlier Clipping - Remove whale/bot influence via quantile clipping.
"""

import logging
from typing import Dict, List
import numpy as np

from specter.config import settings

logger = logging.getLogger(__name__)


class OutlierClipper:
    """Clips extreme outliers to prevent single accounts from dominating the index."""

    def __init__(self, percentile: float = None):
        """Initialize clipper."""
        self.percentile = percentile or settings.CLIP_PERCENTILE

    def clip_metrics(self, metrics: Dict[str, float]) -> Dict[str, any]:
        """
        Clip metrics at percentile threshold.

        Args:
            metrics: Dict of metric values

        Returns:
            {
                "clipped_metrics": {...},  # clipped values
                "clipping_threshold": float,
                "clipped_count": int,
                "metadata": {...}
            }
        """
        if not metrics:
            return {
                "clipped_metrics": {},
                "clipping_threshold": 0.0,
                "clipped_count": 0,
                "metadata": {},
            }

        values = np.array(list(metrics.values()))

        # Compute percentile threshold
        threshold = float(np.percentile(values, self.percentile))

        # Clip values
        clipped_metrics = {}
        clipped_count = 0

        for metric_name, metric_value in metrics.items():
            if metric_value > threshold:
                clipped_metrics[metric_name] = threshold
                clipped_count += 1
            else:
                clipped_metrics[metric_name] = metric_value

        return {
            "clipped_metrics": clipped_metrics,
            "clipping_threshold": threshold,
            "clipped_count": clipped_count,
            "metadata": {
                "percentile": self.percentile,
                "original_max": float(np.max(values)),
                "clipped_max": threshold,
            },
        }
