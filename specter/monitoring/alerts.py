"""
SPECTER Alerting - Send alerts via Telegram for signals and system events.
"""

import logging
import asyncio
from datetime import datetime
from typing import Optional, List

from specter.config import settings
from specter.storage.models import TradeSignal, Trade

logger = logging.getLogger(__name__)

# Try to import telegram bot library
try:
    from telegram import Bot
    from telegram.error import TelegramError
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.warning("python-telegram-bot not installed. Alerts disabled.")


class TelegramAlerts:
    """Sends alerts via Telegram bot."""

    def __init__(self, token: str = None, chat_id: str = None):
        """
        Initialize Telegram alerting.

        Args:
            token: Telegram bot token (default: from config)
            chat_id: Chat ID to send messages to (default: from config)
        """
        if token is None:
            token = settings.TELEGRAM_BOT_TOKEN
        if chat_id is None:
            chat_id = settings.TELEGRAM_CHAT_ID

        if not token or not chat_id:
            logger.warning("Telegram credentials not configured. Alerts disabled.")
            self.enabled = False
            return

        if not TELEGRAM_AVAILABLE:
            logger.warning("python-telegram-bot not installed. Alerts disabled.")
            self.enabled = False
            return

        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.enabled = True

    async def send_message(self, text: str) -> bool:
        """
        Send a message via Telegram.

        Args:
            text: Message text (supports Markdown)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            return True
        except TelegramError as e:
            logger.error(f"Telegram send error: {e}")
            return False

    async def alert_signal(self, signal: TradeSignal) -> bool:
        """Send alert for a trading signal."""
        text = self._format_signal_alert(signal)
        return await self.send_message(text)

    async def alert_execution(
        self,
        topic: str,
        direction: str,
        size: float,
        price: float,
        confidence: float
    ) -> bool:
        """Send alert for a trade execution."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")
        text = (
            f"🟢 *TRADE EXECUTED*\n"
            f"Topic: {topic}\n"
            f"Direction: *{direction.upper()}*\n"
            f"Size: ${size:.2f}\n"
            f"Entry: ${price:.4f}\n"
            f"Confidence: {confidence:.0%}\n"
            f"Time: {timestamp}"
        )
        return await self.send_message(text)

    async def alert_close(
        self,
        topic: str,
        direction: str,
        entry: float,
        exit: float,
        pnl: float,
        pnl_pct: float
    ) -> bool:
        """Send alert for closing a position."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")
        pnl_symbol = "📈" if pnl > 0 else "📉"

        text = (
            f"{pnl_symbol} *POSITION CLOSED*\n"
            f"Topic: {topic} ({direction.upper()})\n"
            f"Entry: ${entry:.4f} → Exit: ${exit:.4f}\n"
            f"P&L: ${pnl:+.2f} ({pnl_pct:+.1f}%)\n"
            f"Time: {timestamp}"
        )
        return await self.send_message(text)

    async def alert_system(self, level: str, message: str) -> bool:
        """Send system alert (info, warning, error)."""
        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(level, "💬")
        timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")

        text = (
            f"{emoji} *SYSTEM {level.upper()}*\n"
            f"{message}\n"
            f"Time: {timestamp}"
        )
        return await self.send_message(text)

    async def alert_error(self, error_type: str, details: str) -> bool:
        """Send error alert."""
        return await self.alert_system("error", f"{error_type}: {details}")

    async def send_heartbeat(self, stats: dict) -> bool:
        """Send periodic heartbeat with system stats."""
        timestamp = datetime.utcnow().strftime("%H:%M:%S UTC")

        text = (
            f"💓 *SPECTER HEARTBEAT*\n"
            f"Status: Running\n"
            f"P&L: ${stats.get('total_pnl', 0):.2f}\n"
            f"Open Positions: {stats.get('open_positions', 0)}\n"
            f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            f"Time: {timestamp}"
        )
        return await self.send_message(text)

    def _format_signal_alert(self, signal: TradeSignal) -> str:
        """Format trading signal as alert message."""
        timestamp = signal.timestamp.strftime("%H:%M:%S UTC")

        # Emoji based on direction
        direction_emoji = "🟢" if signal.direction == "long" else "🔴"

        text = (
            f"{direction_emoji} *NEW SIGNAL*\n"
            f"Topic: *{signal.topic}*\n"
            f"Direction: *{signal.direction.upper()}*\n"
            f"Archetype: {signal.archetype}\n"
            f"Divergence: {signal.divergence:+.1f}%\n"
            f"Confidence: {signal.confidence:.0%}\n"
            f"Price: ${signal.entry_price:.4f}\n"
            f"Reasoning: {signal.reasoning}\n"
            f"Time: {timestamp}"
        )

        return text


# ============================================================================
# Synchronous Wrapper (for blocking code)
# ============================================================================

class AlertsManager:
    """Synchronous wrapper around async Telegram alerts."""

    def __init__(self):
        """Initialize alerts manager."""
        self.alerts = TelegramAlerts()

    def send_signal_alert(self, signal: TradeSignal) -> bool:
        """Send signal alert (synchronous)."""
        if not self.alerts.enabled:
            return False

        try:
            # Create new event loop if needed
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.alerts.alert_signal(signal))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Alert send failed: {e}")
            return False

    def send_execution_alert(
        self,
        topic: str,
        direction: str,
        size: float,
        price: float,
        confidence: float
    ) -> bool:
        """Send trade execution alert."""
        if not self.alerts.enabled:
            return False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.alerts.alert_execution(topic, direction, size, price, confidence)
            )
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Execution alert failed: {e}")
            return False

    def send_close_alert(
        self,
        topic: str,
        direction: str,
        entry: float,
        exit: float,
        pnl: float
    ) -> bool:
        """Send position close alert."""
        if not self.alerts.enabled:
            return False

        pnl_pct = ((exit - entry) / entry * 100) if entry > 0 else 0

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.alerts.alert_close(topic, direction, entry, exit, pnl, pnl_pct)
            )
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Close alert failed: {e}")
            return False

    def send_system_alert(self, level: str, message: str) -> bool:
        """Send system alert."""
        if not self.alerts.enabled:
            logger.warning(f"[{level.upper()}] {message}")
            return False

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.alerts.alert_system(level, message))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"System alert failed: {e}")
            return False
