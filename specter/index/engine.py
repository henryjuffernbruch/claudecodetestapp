"""
SPECTER Engagement Index Engine - Full EI computation pipeline.
Orchestrates: normalize → clip → decay → deseasonalize → smooth
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from specter.storage.models import RawSignal, EngagementIndex
from specter.config import settings
from specter.index.normalizer import EngagementIndexNormalizer
from specter.index.outlier_clipper import OutlierClipper
from specter.index.time_decay import TimeDecayProcessor
from specter.index.deseasonalizer import Deseasonalizer
from specter.index.smoother import Smoother

logger = logging.getLogger(__name__)


class EngagementIndexEngine:
    """Full EI computation pipeline."""

    def __init__(self):
        """Initialize all pipeline components."""
        self.normalizer = EngagementIndexNormalizer()
        self.clipper = OutlierClipper()
        self.decay_processors = {}  # topic -> TimeDecayProcessor
        self.deseasonalizer = Deseasonalizer()
        self.smoother = Smoother()

        # Historical data for decay computation
        self.ei_history = {}  # topic -> [(ei, timestamp), ...]

    def _get_decay_processor(self, topic: str) -> TimeDecayProcessor:
        """Get or create decay processor for topic."""
        if topic not in self.decay_processors:
            half_life = settings.get_decay_half_life(topic)
            self.decay_processors[topic] = TimeDecayProcessor(half_life_hours=half_life)
        return self.decay_processors[topic]

    def _ensure_history(self, topic: str):
        """Ensure history exists for topic."""
        if topic not in self.ei_history:
            self.ei_history[topic] = []

    def compute(
        self,
        topic: str,
        signals: Dict[str, RawSignal],
        current_time: datetime = None
    ) -> EngagementIndex:
        """
        Compute engagement index for a topic from raw signals.

        Pipeline:
        1. Normalize raw metrics to 0-1 scale per platform
        2. Clip outliers (95th percentile)
        3. Apply time decay to historical values
        4. Deseasonalize (remove time-of-day/day-of-week baseline)
        5. Smooth with EMA

        Args:
            topic: Topic name
            signals: Dict of {platform: RawSignal} for this topic
            current_time: Current time (default: now)

        Returns:
            EngagementIndex object
        """
        if current_time is None:
            current_time = datetime.utcnow()

        self._ensure_history(topic)

        # ====================================================================
        # Step 1: Normalize
        # ====================================================================
        platform_eis = {}
        normalized_components = {}

        for platform, signal in signals.items():
            result = self.normalizer.normalize(platform, signal.metrics)
            platform_eis[platform] = result["platform_ei"]
            normalized_components[platform] = result["normalized_metrics"]

        # ====================================================================
        # Step 2: Clip outliers
        # ====================================================================
        all_platform_eis = list(platform_eis.values())
        clip_result = self.clipper.clip_metrics(
            {p: eis for p, eis in platform_eis.items()}
        )
        clipped_platform_eis = clip_result["clipped_metrics"]

        # ====================================================================
        # Step 3: Compute raw EI (weighted average of clipped platform EIs)
        # ====================================================================
        weights = [settings.PLATFORM_WEIGHTS.get(p, 0.0) for p in clipped_platform_eis.keys()]
        platform_values = list(clipped_platform_eis.values())

        if platform_values and sum(weights) > 0:
            # Weighted average
            raw_ei = sum(v * w for v, w in zip(platform_values, weights)) / sum(weights)
        else:
            raw_ei = 0.0

        # Clamp to [0, 1]
        raw_ei = min(1.0, max(0.0, raw_ei))

        # ====================================================================
        # Step 4: Apply time decay (using historical EI values)
        # ====================================================================
        decay_processor = self._get_decay_processor(topic)
        decay_result = decay_processor.apply_decay(
            current_ei=raw_ei,
            current_time=current_time,
            historical_eis=self.ei_history[topic],
            window_hours=24
        )
        decayed_ei = decay_result["decayed_ei"]

        # ====================================================================
        # Step 5: Deseasonalize
        # ====================================================================
        deseason_result = self.deseasonalizer.deseasonalize(
            decayed_ei,
            current_time
        )
        deseasonalized_ei = deseason_result["deseasonalized_ei"]

        # Map back to [0, 1] if needed
        if deseasonalized_ei < 0:
            # Deseasonalized values can be negative, but for now we'll clamp
            deseasonalized_ei = max(0.0, deseasonalized_ei)
        deseasonalized_ei = min(1.0, deseasonalized_ei)

        # ====================================================================
        # Step 6: Smooth with EMA
        # ====================================================================
        smooth_result = self.smoother.smooth(topic, deseasonalized_ei)
        smoothed_ei = smooth_result["smoothed_ei"]

        # ====================================================================
        # Update deseasonalizer baseline (for next iteration)
        # ====================================================================
        self.deseasonalizer.update_baseline(raw_ei, current_time)

        # ====================================================================
        # Update history
        # ====================================================================
        self.ei_history[topic].append((smoothed_ei, current_time))
        # Keep only last 24 hours (1440 minutes at 1-min intervals)
        if len(self.ei_history[topic]) > settings.EI_WINDOW_SIZE:
            self.ei_history[topic] = self.ei_history[topic][-settings.EI_WINDOW_SIZE:]

        # ====================================================================
        # Build EngagementIndex object
        # ====================================================================
        ei = EngagementIndex(
            topic=topic,
            timestamp=current_time,
            raw_ei=raw_ei,
            smoothed_ei=smoothed_ei,
            components={
                "twitter": platform_eis.get("twitter", 0.0),
                "reddit": platform_eis.get("reddit", 0.0),
                "youtube": platform_eis.get("youtube", 0.0),
            },
            metadata={
                "raw_ei": raw_ei,
                "decayed_ei": decayed_ei,
                "deseasonalized_ei": deseasonalized_ei,
                "smoothed_ei": smoothed_ei,
                "clip_stats": clip_result.get("metadata", {}),
                "decay_stats": decay_result.get("metadata", {}),
                "deseason_stats": deseason_result.get("metadata", {}),
                "platforms_contributing": len([p for p in platform_eis.values() if p > 0]),
            },
        )

        logger.info(
            f"[{topic}] EI: raw={raw_ei:.3f}, decay={decayed_ei:.3f}, "
            f"deseason={deseasonalized_ei:.3f}, smooth={smoothed_ei:.3f}"
        )

        return ei

    def compute_batch(
        self,
        signals_by_topic: Dict[str, Dict[str, RawSignal]],
        current_time: datetime = None
    ) -> Dict[str, EngagementIndex]:
        """
        Compute EI for multiple topics.

        Args:
            signals_by_topic: {topic: {platform: RawSignal}}
            current_time: Current time (default: now)

        Returns:
            Dict of {topic: EngagementIndex}
        """
        results = {}

        for topic, signals in signals_by_topic.items():
            try:
                ei = self.compute(topic, signals, current_time)
                results[topic] = ei
            except Exception as e:
                logger.error(f"Failed to compute EI for {topic}: {e}")
                continue

        return results

    def get_history(self, topic: str, limit: int = 100) -> List[tuple]:
        """Get historical EI values for a topic."""
        self._ensure_history(topic)
        return self.ei_history[topic][-limit:]

    def reset(self):
        """Reset all state (for testing)."""
        self.ei_history.clear()
        self.decay_processors.clear()
        self.deseasonalizer.baseline_cache.clear()
        self.smoother.smoothers.clear()
        self.normalizer = EngagementIndexNormalizer()
        logger.info("Engine state reset")
