"""
SPECTER Feature Extraction - Extract features from EI time series for classification.
"""

import logging
from typing import Dict, List, Tuple, Optional
import numpy as np
from scipy import stats

from specter.config import settings

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Extracts classification features from EI time series."""

    @staticmethod
    def extract_first_derivative(ei_window: List[float]) -> float:
        """
        Compute first derivative (rate of change) of EI.

        Returns:
            Slope of EI over the window (can be positive or negative)
        """
        if len(ei_window) < 2:
            return 0.0

        # Use linear regression to get slope
        x = np.arange(len(ei_window))
        y = np.array(ei_window)

        try:
            slope, _, _, _, _ = stats.linregress(x, y)
            return float(slope)
        except:
            return 0.0

    @staticmethod
    def extract_second_derivative(ei_window: List[float]) -> float:
        """
        Compute second derivative (acceleration/deceleration) of EI.

        Returns:
            Change in slope (negative = deceleration, positive = acceleration)
        """
        if len(ei_window) < 4:
            return 0.0

        # Split window in half and compare slopes
        mid = len(ei_window) // 2
        first_half = ei_window[:mid]
        second_half = ei_window[mid:]

        # First slope
        x1 = np.arange(len(first_half))
        y1 = np.array(first_half)
        slope1, _, _, _, _ = stats.linregress(x1, y1) if len(first_half) > 1 else (0, 0, 0, 0, 0)

        # Second slope
        x2 = np.arange(len(second_half))
        y2 = np.array(second_half)
        slope2, _, _, _, _ = stats.linregress(x2, y2) if len(second_half) > 1 else (0, 0, 0, 0, 0)

        # Second derivative is the change in slope
        return float(slope2 - slope1)

    @staticmethod
    def extract_variance_ratio(ei_window: List[float], baseline_variance: float = None) -> float:
        """
        Compute ratio of recent variance to historical variance.

        Args:
            ei_window: Current EI window
            baseline_variance: Historical variance (if None, use first half of window)

        Returns:
            Ratio of recent variance to baseline (< 0.3 indicates plateau)
        """
        if len(ei_window) < 4:
            return 1.0

        # If no baseline provided, use first half of window
        if baseline_variance is None:
            mid = len(ei_window) // 2
            first_half = ei_window[:mid]
            baseline_variance = float(np.var(first_half)) if len(first_half) > 0 else 1.0

        # Recent (second half) variance
        mid = len(ei_window) // 2
        second_half = ei_window[mid:]
        recent_variance = float(np.var(second_half)) if len(second_half) > 0 else 1.0

        # Avoid division by zero
        if baseline_variance < 1e-6:
            return 1.0

        ratio = recent_variance / baseline_variance
        return float(min(10.0, ratio))  # Cap at 10 to avoid extreme outliers

    @staticmethod
    def extract_peak_distance(ei_window: List[float]) -> int:
        """
        Compute how many intervals since the last local maximum.

        Returns:
            Number of intervals (higher = farther from peak)
        """
        if len(ei_window) < 2:
            return 0

        # Find local maxima (simple approach: > both neighbors)
        maxima_indices = []
        for i in range(1, len(ei_window) - 1):
            if ei_window[i] > ei_window[i - 1] and ei_window[i] > ei_window[i + 1]:
                maxima_indices.append(i)

        if not maxima_indices:
            # No local max, check if current is highest
            max_idx = np.argmax(ei_window)
            return len(ei_window) - max_idx - 1

        # Distance from last maximum to end of window
        last_max_idx = maxima_indices[-1]
        distance = len(ei_window) - last_max_idx - 1
        return int(distance)

    @staticmethod
    def extract_autocorrelation(ei_window: List[float], lag: int = 1) -> float:
        """
        Compute autocorrelation at a specific lag.

        Args:
            ei_window: EI time series
            lag: Lag to compute (default: 1)

        Returns:
            Autocorrelation value (-1 to 1, where 1 = perfect positive correlation)
        """
        if len(ei_window) <= lag + 1:
            return 0.0

        y = np.array(ei_window)
        y_lag = np.array(ei_window[lag:])
        y_current = np.array(ei_window[:-lag])

        # Compute Pearson correlation
        try:
            correlation = float(np.corrcoef(y_current, y_lag)[0, 1])
            return min(1.0, max(-1.0, correlation))  # Clamp to [-1, 1]
        except:
            return 0.0

    @staticmethod
    def extract_duration_above_baseline(ei_window: List[float]) -> int:
        """
        Compute how long EI has been elevated above baseline (mean + 1 std).

        Returns:
            Number of consecutive intervals above baseline
        """
        if len(ei_window) < 2:
            return 0

        baseline_mean = float(np.mean(ei_window))
        baseline_std = float(np.std(ei_window))
        threshold = baseline_mean + baseline_std

        # Count from end of window backwards
        duration = 0
        for i in range(len(ei_window) - 1, -1, -1):
            if ei_window[i] > threshold:
                duration += 1
            else:
                break

        return duration

    @staticmethod
    def extract_magnitude(ei_window: List[float], baseline_mean: float = None) -> float:
        """
        Compute current EI deviation from baseline.

        Args:
            ei_window: EI time series
            baseline_mean: Baseline mean (if None, use first half of window)

        Returns:
            Current EI - baseline mean
        """
        if not ei_window:
            return 0.0

        if baseline_mean is None:
            mid = len(ei_window) // 2
            first_half = ei_window[:mid]
            baseline_mean = float(np.mean(first_half)) if len(first_half) > 0 else 0.5

        current_ei = ei_window[-1]
        magnitude = current_ei - baseline_mean
        return float(magnitude)

    @staticmethod
    def extract_volatility_trend(ei_window: List[float]) -> float:
        """
        Compute trend in volatility (is volatility increasing or decreasing).

        Returns:
            Positive if volatility increasing, negative if decreasing
        """
        if len(ei_window) < 8:
            return 0.0

        mid = len(ei_window) // 2
        first_half = ei_window[:mid]
        second_half = ei_window[mid:]

        first_volatility = float(np.std(first_half)) if len(first_half) > 0 else 0.0
        second_volatility = float(np.std(second_half)) if len(second_half) > 0 else 0.0

        trend = second_volatility - first_volatility
        return float(trend)

    @classmethod
    def extract_all(cls, ei_window: List[float]) -> Dict[str, float]:
        """
        Extract all classification features from EI window.

        Args:
            ei_window: List of EI values (ordered chronologically)

        Returns:
            Dict of {feature_name: feature_value}
        """
        if len(ei_window) < 2:
            logger.warning(f"EI window too small for feature extraction: {len(ei_window)}")
            return {}

        features = {
            "first_derivative": cls.extract_first_derivative(ei_window),
            "second_derivative": cls.extract_second_derivative(ei_window),
            "variance_ratio": cls.extract_variance_ratio(ei_window),
            "peak_distance": cls.extract_peak_distance(ei_window),
            "autocorrelation_lag1": cls.extract_autocorrelation(ei_window, lag=1),
            "autocorrelation_lag24": cls.extract_autocorrelation(ei_window, lag=min(24, len(ei_window) - 1)),
            "duration_above_baseline": cls.extract_duration_above_baseline(ei_window),
            "magnitude": cls.extract_magnitude(ei_window),
            "volatility_trend": cls.extract_volatility_trend(ei_window),
        }

        return features

    @staticmethod
    def standardize_features(features: Dict[str, float]) -> Dict[str, float]:
        """
        Standardize features to similar scales for classification.

        Args:
            features: Dict of {feature_name: feature_value}

        Returns:
            Standardized features
        """
        # Define expected ranges for normalization
        ranges = {
            "first_derivative": (-0.1, 0.1),
            "second_derivative": (-0.05, 0.05),
            "variance_ratio": (0.0, 1.0),
            "peak_distance": (0, 30),
            "autocorrelation_lag1": (-1.0, 1.0),
            "autocorrelation_lag24": (-1.0, 1.0),
            "duration_above_baseline": (0, 30),
            "magnitude": (-1.0, 1.0),
            "volatility_trend": (-0.1, 0.1),
        }

        standardized = {}
        for feature_name, feature_value in features.items():
            if feature_name in ranges:
                min_val, max_val = ranges[feature_name]
                # Normalize to [0, 1]
                if max_val - min_val > 0:
                    normalized = (feature_value - min_val) / (max_val - min_val)
                    # Clamp to [0, 1]
                    normalized = min(1.0, max(0.0, normalized))
                    standardized[feature_name] = float(normalized)
                else:
                    standardized[feature_name] = 0.0
            else:
                standardized[feature_name] = feature_value

        return standardized
