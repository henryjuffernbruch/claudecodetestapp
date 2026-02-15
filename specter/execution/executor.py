"""
SPECTER Trade Executor - Execute trades on Kalshi with paper trading mode.
Paper mode for first 3-5 days of validation before live trading.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from specter.storage.models import Trade, TradeSignal
from specter.storage.timeseries_db import TimeseriesDB
from specter.execution.kalshi_client import KalshiClient
from specter.execution.position_sizer import PositionSizer
from specter.signals.kalshi_mapper import get_mapper
from specter.config import settings

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Executes trades on Kalshi with paper trading mode."""

    def __init__(
        self,
        trading_mode: str = None,
        initial_bankroll: float = None,
        db: TimeseriesDB = None
    ):
        """
        Initialize executor.

        Args:
            trading_mode: "paper" or "live" (default: from settings)
            initial_bankroll: Starting bankroll (default: from settings)
            db: Database instance for logging trades
        """
        self.trading_mode = trading_mode or settings.TRADING_MODE
        self.initial_bankroll = initial_bankroll or settings.INITIAL_BANKROLL
        self.current_bankroll = self.initial_bankroll
        self.db = db
        self.mapper = get_mapper()

        # Initialize Kalshi client (only in live mode)
        if self.trading_mode == "live":
            self.kalshi = KalshiClient()
            if not self.kalshi.health_check():
                logger.warning("Kalshi API not responding. Paper mode recommended.")
        else:
            self.kalshi = None

        # Position sizer
        self.position_sizer = PositionSizer(self.current_bankroll)

        # Track open positions and daily P&L
        self.open_positions = {}  # position_id -> Trade object
        self.daily_pnl = 0.0
        self.daily_pnl_reset_time = datetime.utcnow()

        logger.info(
            f"Trade executor initialized: mode={self.trading_mode}, "
            f"bankroll=${self.current_bankroll:.2f}"
        )

    def _reset_daily_pnl(self):
        """Reset daily P&L at midnight."""
        now = datetime.utcnow()
        if now.date() > self.daily_pnl_reset_time.date():
            self.daily_pnl = 0.0
            self.daily_pnl_reset_time = now
            logger.info("Daily P&L reset")

    def execute_signal(
        self,
        signal: TradeSignal,
        current_price: Optional[float] = None
    ) -> Optional[Trade]:
        """
        Execute a trading signal.

        Args:
            signal: TradeSignal to execute
            current_price: Current market price (default: from Kalshi API)

        Returns:
            Trade object if executed, None otherwise
        """
        self._reset_daily_pnl()

        # Check if topic is tradeable
        if not self.mapper.is_tradeable(signal.topic):
            logger.warning(f"Topic {signal.topic} not tradeable")
            return None

        # Check daily loss limit
        if self.daily_pnl < -self.current_bankroll * settings.DAILY_LOSS_LIMIT_PCT:
            logger.warning(
                f"Daily loss limit reached (loss: {self.daily_pnl:.2f}). "
                f"Stopping trades."
            )
            return None

        # Get contract details
        contract_mapping = self.mapper.get_contract_for_topic(signal.topic)
        if not contract_mapping:
            logger.error(f"No contract mapping for {signal.topic}")
            return None

        # Determine contract ticker
        # Note: In production, need to get actual contract IDs from Kalshi API
        contract_family = contract_mapping.get("contract_family")
        contract_ticker = f"{contract_family}-0000"  # Placeholder format

        # Get current price if not provided
        if current_price is None:
            if self.trading_mode == "live":
                current_price = self.kalshi.get_contract_price(
                    contract_ticker,
                    signal.direction
                )
            else:
                # Paper trading: assume mid-market price
                current_price = 0.5

        if current_price is None:
            logger.error(f"Could not get price for {contract_ticker}")
            return None

        # Position sizing
        sizing = self.position_sizer.get_risk_adjusted_size(
            signal.confidence,
            self.daily_pnl
        )

        position_size = sizing["position_size_usd"]

        if position_size < 1.0:
            logger.info(
                f"Position too small ({position_size:.2f}). "
                f"Skipping trade."
            )
            return None

        # Compute shares
        shares = self.position_sizer.compute_shares(position_size, current_price)

        if shares < 1:
            logger.info(f"Position size doesn't translate to shares. Skipping.")
            return None

        logger.info(
            f"[{self.trading_mode.upper()}] Executing {signal.topic} {signal.direction.upper()} | "
            f"Shares: {shares} | Price: ${current_price:.4f} | "
            f"Size: ${position_size:.2f} | Confidence: {signal.confidence:.0%}"
        )

        # Create Trade object
        trade_id = str(uuid.uuid4())
        trade = Trade(
            id=trade_id,
            topic=signal.topic,
            venue=signal.venue,
            direction=signal.direction,
            entry_price=current_price,
            entry_size=position_size,
            exit_price=None,
            exit_size=None,
            pnl=None,
            signal_confidence=signal.confidence,
            signal_archetype=signal.archetype,
            opened_at=signal.timestamp,
            closed_at=None,
            status="open",
            notes=None,
        )

        # Execute based on mode
        if self.trading_mode == "paper":
            # Paper trading: just log it
            logger.info(f"[PAPER] Trade {trade_id} logged (not executed)")
        elif self.trading_mode == "live":
            # Live trading: execute on Kalshi
            try:
                # Map signal direction to contract side (yes/no)
                contract_side = "yes" if signal.direction == "long" else "no"

                order = self.kalshi.place_order(
                    contract_ticker=contract_ticker,
                    side=contract_side,
                    quantity=shares,
                    price=current_price
                )

                if not order:
                    logger.error(f"Order placement failed for {signal.topic}")
                    return None

                logger.info(f"[LIVE] Order placed: {order}")
                trade.notes = f"Kalshi order: {order.get('id')}"

            except Exception as e:
                logger.error(f"Trade execution error: {e}")
                return None

        # Log to database
        if self.db:
            self.db.insert_trade(trade)

        # Track position
        self.open_positions[trade_id] = trade

        # Update bankroll (reduce by position size)
        self.current_bankroll -= position_size
        self.position_sizer.update_bankroll(self.current_bankroll)

        return trade

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = "signal_exit"
    ) -> Optional[Trade]:
        """
        Close an open position.

        Args:
            position_id: Position ID to close
            exit_price: Exit price
            reason: Reason for closing

        Returns:
            Updated Trade object
        """
        if position_id not in self.open_positions:
            logger.warning(f"Position {position_id} not found")
            return None

        trade = self.open_positions[position_id]

        # Compute P&L
        if trade.direction == "long":
            pnl = (exit_price - trade.entry_price) * (trade.entry_size / trade.entry_price)
        else:  # short
            pnl = (trade.entry_price - exit_price) * (trade.entry_size / trade.entry_price)

        # Update trade
        trade.exit_price = exit_price
        trade.exit_size = trade.entry_size
        trade.pnl = pnl
        trade.closed_at = datetime.utcnow()
        trade.status = "closed"
        trade.notes = f"Closed: {reason}"

        # Update P&L tracking
        self.daily_pnl += pnl
        self.current_bankroll += trade.entry_size + pnl
        self.position_sizer.update_bankroll(self.current_bankroll)

        # Log to database
        if self.db:
            self.db.update_trade(trade)

        # Remove from open positions
        del self.open_positions[position_id]

        logger.info(
            f"Position {position_id} closed: ${pnl:+.2f} P&L ({pnl/trade.entry_size:+.1%})"
        )

        return trade

    def check_position_timeouts(self, timeout_minutes: int = None) -> List[str]:
        """
        Check for positions that have been open too long and close them.

        Args:
            timeout_minutes: Max minutes to hold position (default: from settings)

        Returns:
            List of closed position IDs
        """
        if timeout_minutes is None:
            timeout_minutes = settings.POSITION_TIMEOUT_MINUTES

        closed = []
        now = datetime.utcnow()

        for position_id, trade in list(self.open_positions.items()):
            age = (now - trade.opened_at).total_seconds() / 60

            if age > timeout_minutes:
                logger.warning(
                    f"Position {position_id} exceeded timeout "
                    f"({age:.0f}min > {timeout_minutes}min). Closing."
                )

                # Close at market (0.5 estimate for paper mode)
                exit_price = 0.5

                if self.trading_mode == "live":
                    # Get actual market price
                    # (placeholder, would need real price from Kalshi)
                    exit_price = 0.5

                self.close_position(position_id, exit_price, "timeout")
                closed.append(position_id)

        return closed

    def check_stoploss(self, hard_stoploss_pct: float = None) -> List[str]:
        """
        Check for positions that have hit hard stop-loss and close them.

        Args:
            hard_stoploss_pct: Hard stop-loss threshold (default: from settings)

        Returns:
            List of closed position IDs
        """
        if hard_stoploss_pct is None:
            hard_stoploss_pct = settings.HARD_STOPLOSS_PCT

        closed = []

        for position_id, trade in list(self.open_positions.items()):
            # Estimate current price (would be from market data in production)
            current_price = 0.5  # Placeholder

            # Compute P&L
            if trade.direction == "long":
                loss_pct = (trade.entry_price - current_price) / trade.entry_price
            else:
                loss_pct = (current_price - trade.entry_price) / trade.entry_price

            if loss_pct > hard_stoploss_pct:
                logger.warning(
                    f"Position {position_id} hit hard stop-loss "
                    f"({loss_pct:.1%} > {hard_stoploss_pct:.1%}). Closing."
                )

                self.close_position(position_id, current_price, "hard_stoploss")
                closed.append(position_id)

        return closed

    def get_status(self) -> Dict:
        """Get executor status."""
        return {
            "mode": self.trading_mode,
            "bankroll": self.current_bankroll,
            "initial_bankroll": self.initial_bankroll,
            "open_positions": len(self.open_positions),
            "daily_pnl": self.daily_pnl,
            "daily_pnl_pct": self.daily_pnl / self.initial_bankroll,
        }
