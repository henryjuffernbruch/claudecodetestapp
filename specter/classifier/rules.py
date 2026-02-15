"""
SPECTER Rule-Based Classifier - Classify decay patterns using heuristic rules.
Phase 1 classifier (ML version in Phase 4).
"""

import logging
from typing import Dict, Tuple, List
from scipy import stats

from specter.config import settings
from specter.classifier.archetypes import (
    ARCHETYPE_SPIKE_DECAY, ARCHETYPE_PLATEAU_CLIFF, ARCHETYPE_SLOW_BUILD,
    ARCHETYPE_OSCILLATION, ARCHETYPE_UNKNOWN
)
from specter.classifier.features import FeatureExtractor

logger = logging.getLogger(__name__)


class RuleBasedClassifier:
    """
    Rule-based decay pattern classifier.

    Classifies 4 archetypes:
    1. SPIKE_DECAY - sharp impulse + consistent decay
    2. PLATEAU_CLIFF - sustained + sudden drop
    3. SLOW_BUILD - rising with acceleration
    4. OSCILLATION - periodic pattern
    """

    def __init__(self):
        """Initialize classifier."""
        self.feature_extractor = FeatureExtractor()

    def classify(self, ei_window: List[float]) -> Tuple[str, float, Dict]:
        """
        Classify decay pattern from EI window.

        Args:
            ei_window: List of EI values (ordered chronologically, at least 30 intervals)

        Returns:
            (archetype, confidence, features_dict)
        """
        if len(ei_window) < 10:
            logger.warning(f"EI window too small for classification: {len(ei_window)}")
            return ARCHETYPE_UNKNOWN, 0.0, {}

        # Extract features
        features = self.feature_extractor.extract_all(ei_window)

        # Normalize features for interpretation
        std_features = self.feature_extractor.standardize_features(features)

        # Get baseline stats
        baseline_mean = float(stats.mean(ei_window[:len(ei_window)//2]))
        baseline_std = float(stats.stdev(ei_window[:len(ei_window)//2])) if len(ei_window) > 4 else 1.0
        if baseline_std < 1e-6:
            baseline_std = 1.0

        # ====================================================================
        # Classify using rules
        # ====================================================================

        # Score each archetype
        scores = {
            ARCHETYPE_SPIKE_DECAY: self._score_spike_decay(features, ei_window),
            ARCHETYPE_PLATEAU_CLIFF: self._score_plateau_cliff(features, ei_window),
            ARCHETYPE_SLOW_BUILD: self._score_slow_build(features, ei_window),
            ARCHETYPE_OSCILLATION: self._score_oscillation(features, ei_window),
        }

        # Find highest scoring archetype
        best_archetype = max(scores, key=scores.get)
        best_score = scores[best_archetype]

        # Confidence: normalized score (0-1)
        max_possible_score = 1.0
        confidence = min(1.0, best_score / max_possible_score)

        return best_archetype, confidence, features

    def _score_spike_decay(self, features: Dict, ei_window: List[float]) -> float:
        """Score likelihood of SPIKE_DECAY pattern."""
        score = 0.0

        # Strong indicator: positive first derivative in past, now negative second derivative
        first_deriv = features.get("first_derivative", 0.0)
        second_deriv = features.get("second_derivative", 0.0)
        variance_ratio = features.get("variance_ratio", 1.0)

        # Check if we're in decay phase (negative 2nd derivative)
        if second_deriv < -0.01:
            score += 0.4

        # Check if we recently had positive first deriv (was rising)
        # Look at first half of window
        first_half = ei_window[:len(ei_window)//2]
        first_half_slope, _, _, _, _ = stats.linregress(
            list(range(len(first_half))), first_half
        ) if len(first_half) > 1 else (0, 0, 0, 0, 0)

        if first_half_slope > 0.01:
            score += 0.3

        # Low variance ratio indicates stable plateau (not spike decay)
        if variance_ratio > 0.3:
            score += 0.2

        # Peak distance small means we're close to peak
        peak_distance = features.get("peak_distance", 0)
        if peak_distance < 10:
            score += 0.1

        return score

    def _score_plateau_cliff(self, features: Dict, ei_window: List[float]) -> float:
        """Score likelihood of PLATEAU_CLIFF pattern."""
        score = 0.0

        variance_ratio = features.get("variance_ratio", 1.0)
        first_deriv = features.get("first_derivative", 0.0)
        duration_above_baseline = features.get("duration_above_baseline", 0)

        # Main indicator: low variance (sustained plateau)
        if variance_ratio < settings.PLATEAU_VARIANCE_RATIO_THRESHOLD:
            score += 0.5

        # And long duration at elevated level
        if duration_above_baseline > settings.PLATEAU_MIN_DURATION_INTERVALS:
            score += 0.3

        # Negative first derivative suggests cliff is forming
        if first_deriv < -0.02:
            score += 0.2

        return score

    def _score_slow_build(self, features: Dict, ei_window: List[float]) -> float:
        """Score likelihood of SLOW_BUILD pattern."""
        score = 0.0

        first_deriv = features.get("first_derivative", 0.0)
        second_deriv = features.get("second_derivative", 0.0)
        magnitude = features.get("magnitude", 0.0)

        # Main indicators: positive derivatives (rising with acceleration)
        if first_deriv > 0.01:
            score += 0.3

        if second_deriv > 0.005:  # Accelerating
            score += 0.3

        # Not yet too elevated (< 1.5x baseline)
        if magnitude < 0.5:
            score += 0.2

        # Count positive first deriv periods
        num_positive_periods = 0
        for i in range(1, len(ei_window)):
            if ei_window[i] > ei_window[i-1]:
                num_positive_periods += 1

        if num_positive_periods > len(ei_window) * 0.6:  # >60% rising
            score += 0.2

        return score

    def _score_oscillation(self, features: Dict, ei_window: List[float]) -> float:
        """Score likelihood of OSCILLATION pattern."""
        score = 0.0

        autocorr_lag1 = features.get("autocorrelation_lag1", 0.0)
        autocorr_lag24 = features.get("autocorrelation_lag24", 0.0)
        magnitude = features.get("magnitude", 0.0)

        # Main indicator: autocorrelation at a lag
        # For oscillation, we'd expect to see periodic correlation
        if abs(autocorr_lag24) > settings.OSCILLATION_AUTOCORR_THRESHOLD:
            score += 0.5

        # Or strong lag-1 autocorrelation (persistence)
        if abs(autocorr_lag1) > 0.7:
            score += 0.3

        # Oscillation returns to mean, so magnitude shouldn't be too high
        if abs(magnitude) < 0.3:
            score += 0.2

        return score

    def classify_batch(self, signals_by_topic: Dict[str, List[float]]) -> Dict[str, Tuple[str, float]]:
        """
        Classify multiple topics.

        Args:
            signals_by_topic: {topic: [ei_values]}

        Returns:
            {topic: (archetype, confidence)}
        """
        results = {}

        for topic, ei_window in signals_by_topic.items():
            try:
                archetype, confidence, features = self.classify(ei_window)
                results[topic] = (archetype, confidence)
            except Exception as e:
                logger.error(f"Classification failed for {topic}: {e}")
                results[topic] = (ARCHETYPE_UNKNOWN, 0.0)

        return results
