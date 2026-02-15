"""
SPECTER Signal Generator - Generate trading signals from classifier + divergence.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from specter.storage.models import TradeSignal, EngagementIndex, Classification
from specter.classifier.rules import RuleBasedClassifier
from specter.signals.divergence import DivergenceDetector
from specter.signals.kalshi_mapper import get_mapper
from specter.config import settings

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates trading signals from EI classification and divergence."""

    def __init__(self):
        """Initialize signal generator."""
        self.classifier = RuleBasedClassifier()
        self.divergence_detector = DivergenceDetector()
        self.mapper = get_mapper()
        self.ei_history = {}  # topic -> [ei_values]

    def update_ei(self, ei: EngagementIndex):
        """Update EI for a topic."""
        if ei.topic not in self.ei_history:
            self.ei_history[ei.topic] = []

        self.ei_history[ei.topic].append(ei.smoothed_ei)

        # Keep only last 60 values for classification
        if len(self.ei_history[ei.topic]) > 60:
            self.ei_history[ei.topic] = self.ei_history[ei.topic][-60:]

        # Update divergence detector
        self.divergence_detector.update_ei(ei.topic, ei.smoothed_ei, ei.timestamp)

    def update_price(self, topic: str, price: float, timestamp: datetime):
        """Update market price for a topic (called when price data available)."""
        self.divergence_detector.update_price(topic, price, timestamp)

    def generate_signal(
        self,
        topic: str,
        ei: EngagementIndex,
        current_price: Optional[float] = None
    ) -> Optional[TradeSignal]:
        """
        Generate trading signal for a topic.

        Returns:
            TradeSignal object if conditions met, None otherwise
        """
        # Check if topic is tradeable
        if not self.mapper.is_tradeable(topic):
            logger.debug(f"Topic {topic} not tradeable on Kalshi")
            return None

        # Get EI history for classification
        if topic not in self.ei_history or len(self.ei_history[topic]) < 10:
            logger.debug(f"Insufficient EI history for {topic}")
            return None

        ei_window = self.ei_history[topic]

        # ====================================================================
        # Step 1: Classify decay pattern
        # ====================================================================
        archetype, confidence, features = self.classifier.classify(ei_window)

        # ====================================================================
        # Step 2: Detect divergence (if price data available)
        # ====================================================================
        divergence_pct = None
        if current_price is not None:
            self.update_price(topic, current_price, ei.timestamp)

        div_result = self.divergence_detector.compute_divergence(topic, window_intervals=10)

        if div_result is None:
            logger.debug(f"Insufficient price history for divergence detection on {topic}")
            return None

        divergence_pct = div_result["divergence_pct"]

        # ====================================================================
        # Step 3: Generate signal based on divergence threshold
        # ====================================================================
        abs_divergence = abs(divergence_pct)

        # Only signal if divergence exceeds threshold
        if abs_divergence < settings.DIVERGENCE_ENTRY_THRESHOLD:
            logger.debug(
                f"[{topic}] Divergence too small: {divergence_pct:.1f}% "
                f"(threshold: {settings.DIVERGENCE_ENTRY_THRESHOLD}%)"
            )
            return None

        # Determine direction based on divergence
        direction = self.mapper.get_direction(topic, divergence_pct)

        if direction is None:
            logger.warning(f"Could not determine trade direction for {topic}")
            return None

        # ====================================================================
        # Step 4: Compute signal confidence and reasoning
        # ====================================================================
        signal_confidence = self._compute_confidence(
            archetype,
            confidence,
            divergence_pct,
            div_result
        )

        reasoning = self._generate_reasoning(
            topic,
            archetype,
            confidence,
            divergence_pct,
            direction
        )

        # ====================================================================
        # Step 5: Create TradeSignal object
        # ====================================================================
        signal = TradeSignal(
            topic=topic,
            venue="kalshi",
            direction=direction,
            confidence=signal_confidence,
            archetype=archetype,
            divergence=divergence_pct,
            entry_price=current_price or 0.5,  # Default if no price available
            timestamp=ei.timestamp,
            reasoning=reasoning,
        )

        logger.info(
            f"[SIGNAL] {topic} {direction.upper()} | "
            f"Archetype: {archetype} ({confidence:.2f}) | "
            f"Divergence: {divergence_pct:.1f}% | "
            f"Confidence: {signal_confidence:.2f}"
        )

        return signal

    def generate_signals_batch(
        self,
        eis_by_topic: Dict[str, EngagementIndex],
        prices_by_topic: Dict[str, float] = None
    ) -> List[TradeSignal]:
        """
        Generate signals for multiple topics.

        Args:
            eis_by_topic: {topic: EngagementIndex}
            prices_by_topic: {topic: current_price} (optional)

        Returns:
            List of TradeSignal objects
        """
        if prices_by_topic is None:
            prices_by_topic = {}

        signals = []

        for topic, ei in eis_by_topic.items():
            # Update EI history
            self.update_ei(ei)

            # Generate signal
            price = prices_by_topic.get(topic)
            signal = self.generate_signal(topic, ei, price)

            if signal:
                signals.append(signal)

        return signals

    def _compute_confidence(
        self,
        archetype: str,
        classifier_confidence: float,
        divergence_pct: float,
        div_result: Dict
    ) -> float:
        """
        Compute overall signal confidence (0-1).

        Factors:
        - Archetype confidence (how well does pattern match)
        - Divergence magnitude (how strong is the signal)
        - Consistency (EI and price both moving as expected)
        """
        # Normalize divergence contribution (cap at 25% strong signal)
        div_contribution = min(1.0, abs(divergence_pct) / settings.DIVERGENCE_STRONG_THRESHOLD)

        # Combine factors
        combined = (
            classifier_confidence * 0.4 +    # 40% from archetype
            div_contribution * 0.6             # 60% from divergence
        )

        return float(min(1.0, max(0.0, combined)))

    def _generate_reasoning(
        self,
        topic: str,
        archetype: str,
        classifier_conf: float,
        divergence_pct: float,
        direction: str
    ) -> str:
        """Generate human-readable reasoning for the signal."""
        reason_parts = [
            f"{topic} attention pattern: {archetype} (confidence: {classifier_conf:.0%})",
            f"Divergence: EI {'+' if divergence_pct > 0 else ''}{divergence_pct:.1f}% vs market",
            f"Direction: {direction.upper()}"
        ]

        if divergence_pct > 0:
            reason_parts.append("EI rising faster than price: expect upside")
        else:
            reason_parts.append("EI falling faster than price: expect downside")

        return " | ".join(reason_parts)

    def get_diagnostics(self, topic: str) -> Dict:
        """Get diagnostic info for a topic."""
        ei_history = self.ei_history.get(topic, [])
        div_diags = self.divergence_detector.get_diagnostics(topic)

        archetype = "N/A"
        confidence = 0.0
        if ei_history and len(ei_history) >= 10:
            archetype, confidence, _ = self.classifier.classify(ei_history)

        return {
            "topic": topic,
            "ei_history_length": len(ei_history),
            "archetype": archetype,
            "classifier_confidence": confidence,
            "divergence": div_diags,
        }
