"""
SPECTER Position Sizer - Kelly Criterion sizing with risk management.
"""

import logging
from typing import Dict, Optional

from specter.config import settings

logger = logging.getLogger(__name__)


class PositionSizer:
    """
    Computes position sizes using Kelly Criterion.

    Kelly Criterion: f* = (bp - q) / b
    where:
        b = odds offered (win to loss ratio)
        p = probability of winning
        q = 1 - p (probability of losing)
        f* = fraction of bankroll to risk

    We use fractional Kelly (e.g., 0.25 Kelly) for safety.
    """

    def __init__(
        self,
        bankroll: float = None,
        kelly_fraction: float = None,
        max_risk_per_trade: float = None
    ):
        """
        Initialize position sizer.

        Args:
            bankroll: Total bankroll in USD (default: from settings)
            kelly_fraction: Fractional Kelly to use (default: 0.25)
            max_risk_per_trade: Max % of bankroll to risk (default: 10%)
        """
        self.bankroll = bankroll or settings.INITIAL_BANKROLL
        self.kelly_fraction = kelly_fraction or settings.KELLY_FRACTION
        self.max_risk_per_trade = max_risk_per_trade or settings.MAX_RISK_PER_TRADE

        logger.info(
            f"Position sizer: bankroll=${self.bankroll:.2f}, "
            f"kelly={self.kelly_fraction}, "
            f"max_risk={self.max_risk_per_trade:.1%}"
        )

    def update_bankroll(self, new_bankroll: float):
        """Update bankroll (e.g., after a trade closes)."""
        self.bankroll = new_bankroll

    def compute_kelly_size(
        self,
        win_probability: float,
        loss_ratio: float = 1.0
    ) -> float:
        """
        Compute position size using full Kelly Criterion.

        Args:
            win_probability: Estimated probability of trade winning (0-1)
            loss_ratio: Ratio of average loss to average win (default: 1.0 for 50/50)

        Returns:
            Fraction of bankroll to use (0-1)
        """
        if not (0 < win_probability < 1):
            return 0.0

        # Kelly formula: f* = (bp - q) / b
        # where b = loss_ratio, p = win_prob, q = 1 - win_prob
        b = loss_ratio
        p = win_probability
        q = 1.0 - p

        kelly_size = (b * p - q) / b

        # Ensure non-negative
        kelly_size = max(0.0, kelly_size)

        # Apply fractional Kelly
        fractional = kelly_size * self.kelly_fraction

        return min(1.0, fractional)  # Cap at 100% bankroll

    def compute_position_size(
        self,
        signal_confidence: float,
        current_bankroll: float = None,
        loss_ratio: float = 1.0
    ) -> Dict[str, float]:
        """
        Compute actual position size in USD.

        Args:
            signal_confidence: Signal confidence score (0-1)
            current_bankroll: Current bankroll (default: stored)
            loss_ratio: Ratio of avg loss to avg win (default: 1.0)

        Returns:
            {
                "kelly_fraction": float,  # Kelly fraction (0-1)
                "position_size_usd": float,  # Actual size to trade
                "risk_amount_usd": float,  # Max loss if wrong
                "risk_pct": float,  # Risk as % of bankroll
                "max_position_size": float,  # Max allowed by limits
            }
        """
        if current_bankroll is None:
            current_bankroll = self.bankroll

        # Treat signal confidence as win probability
        win_prob = signal_confidence

        # Compute Kelly size
        kelly_fraction = self.compute_kelly_size(win_prob, loss_ratio)

        # Kelly-based position size
        kelly_position_size = kelly_fraction * current_bankroll

        # Hard cap: max risk per trade
        max_position_size = current_bankroll * self.max_risk_per_trade

        # Actual position size (take minimum)
        position_size = min(kelly_position_size, max_position_size)

        # Risk amount (assuming 50/50 odds, roughly half the position)
        risk_amount = position_size * 0.5  # Conservative estimate

        risk_pct = (risk_amount / current_bankroll) if current_bankroll > 0 else 0.0

        return {
            "kelly_fraction": kelly_fraction,
            "position_size_usd": position_size,
            "risk_amount_usd": risk_amount,
            "risk_pct": risk_pct,
            "max_position_size": max_position_size,
        }

    def compute_shares(
        self,
        position_size_usd: float,
        contract_price: float
    ) -> int:
        """
        Convert USD position size to number of contract shares.

        For a contract priced at P, buying 1 share costs $P.
        Total cost = shares * price

        Args:
            position_size_usd: Position size in USD
            contract_price: Contract price (0-1)

        Returns:
            Number of shares to buy
        """
        if contract_price < 1e-6:
            return 0

        shares = int(position_size_usd / contract_price)
        return max(0, shares)

    def get_risk_adjusted_size(
        self,
        signal_confidence: float,
        daily_pnl: float,
        daily_loss_limit_pct: float = None
    ) -> Dict[str, float]:
        """
        Adjust position size based on daily P&L (avoid over-risking after losses).

        Args:
            signal_confidence: Signal confidence (0-1)
            daily_pnl: Daily P&L (negative = loss)
            daily_loss_limit_pct: Max daily loss % (default: from settings)

        Returns:
            Adjusted position sizing dict
        """
        if daily_loss_limit_pct is None:
            daily_loss_limit_pct = settings.DAILY_LOSS_LIMIT_PCT

        # Check daily loss limit
        daily_loss_pct = abs(daily_pnl) / self.bankroll if daily_pnl < 0 else 0
        remaining_risk = daily_loss_limit_pct - daily_loss_pct

        if remaining_risk <= 0:
            logger.warning(f"Daily loss limit reached. Stopping trades.")
            return {
                "kelly_fraction": 0.0,
                "position_size_usd": 0.0,
                "risk_amount_usd": 0.0,
                "risk_pct": 0.0,
                "max_position_size": 0.0,
                "reason": "daily_loss_limit_reached",
            }

        # Otherwise compute normally (position sizing will naturally be smaller after losses)
        sizing = self.compute_position_size(signal_confidence)

        # Verify against remaining daily risk
        if sizing["risk_pct"] > remaining_risk:
            # Reduce position size proportionally
            scaling_factor = remaining_risk / sizing["risk_pct"]
            sizing["position_size_usd"] *= scaling_factor
            sizing["risk_amount_usd"] *= scaling_factor
            sizing["risk_pct"] = remaining_risk
            sizing["reason"] = "scaled_for_daily_limit"

        return sizing

    def get_sizing_diagnostics(self) -> Dict:
        """Get current sizing diagnostics."""
        return {
            "bankroll": self.bankroll,
            "kelly_fraction": self.kelly_fraction,
            "max_risk_per_trade": self.max_risk_per_trade,
            "max_position_usd": self.bankroll * self.max_risk_per_trade,
        }
