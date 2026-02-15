"""
SPECTER Kalshi Client - REST API wrapper for Kalshi trading platform.
"""

import logging
import json
import time
from typing import Dict, List, Optional
import hmac
import hashlib
from datetime import datetime
import requests

from specter.config import settings

logger = logging.getLogger(__name__)


class KalshiClient:
    """REST API client for Kalshi platform."""

    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize Kalshi client.

        Args:
            api_key: API key (default: from config)
            api_secret: API secret (default: from config)
        """
        self.api_key = api_key or settings.KALSHI_API_KEY
        self.api_secret = api_secret or settings.KALSHI_API_SECRET
        self.base_url = settings.KALSHI_API_BASE_URL
        self.session = requests.Session()
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Conservative rate limiting

        if not self.api_key or not self.api_secret:
            logger.warning("Kalshi API credentials not configured")

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _sign_request(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """
        Generate HMAC signature for request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (e.g., "/exchange/v2/markets")
            body: Request body (for POST/PUT)

        Returns:
            Headers dict with Authorization and signature
        """
        # Timestamp in milliseconds
        timestamp = str(int(time.time() * 1000))

        # Create signature string: METHOD|PATH|TIMESTAMP|BODY
        signature_string = f"{method}|{path}|{timestamp}|{body}"

        # HMAC-SHA256
        signature = hmac.new(
            self.api_secret.encode(),
            signature_string.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "Authorization": f"{self.api_key}:{signature}",
            "Kalshi-Timestamp": timestamp,
            "Content-Type": "application/json",
        }

        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[Dict] = None,
        retries: int = 3
    ) -> Optional[Dict]:
        """
        Make API request with retry logic.

        Args:
            method: HTTP method
            path: Request path
            body: Request body (for POST/PUT)
            retries: Number of retries

        Returns:
            Response JSON, or None on failure
        """
        self._rate_limit()

        url = self.base_url + path
        body_str = json.dumps(body) if body else ""
        headers = self._sign_request(method, path, body_str)

        for attempt in range(retries):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=body_str if body_str else None,
                    timeout=10,
                )

                if response.status_code == 200 or response.status_code == 201:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited, backoff and retry
                    wait = 2 ** attempt
                    logger.warning(f"Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                elif response.status_code == 401:
                    logger.error("Authentication failed. Check API credentials.")
                    return None
                else:
                    logger.error(
                        f"API error {response.status_code}: {response.text}"
                    )
                    return None

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{retries})")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        return None

    # ========================================================================
    # Market Methods
    # ========================================================================

    def get_markets(self) -> Optional[List[Dict]]:
        """Get all available markets."""
        result = self._request("GET", "/exchange/v2/markets")
        if result and "markets" in result:
            return result["markets"]
        return None

    def get_market(self, contract_ticker: str) -> Optional[Dict]:
        """Get market details for a specific contract."""
        result = self._request("GET", f"/exchange/v2/markets/{contract_ticker}")
        return result

    def get_orderbook(self, contract_ticker: str) -> Optional[Dict]:
        """Get orderbook for a contract."""
        result = self._request("GET", f"/exchange/v2/markets/{contract_ticker}/orderbook")
        if result:
            return {
                "yes_price": result.get("yes_bid", 0.5),
                "no_price": result.get("no_ask", 0.5),
                "yes_bid": result.get("yes_bid"),
                "yes_ask": result.get("yes_ask"),
                "no_bid": result.get("no_bid"),
                "no_ask": result.get("no_ask"),
            }
        return None

    # ========================================================================
    # Order Methods
    # ========================================================================

    def place_order(
        self,
        contract_ticker: str,
        side: str,  # "yes" or "no"
        quantity: int,  # Number of shares
        price: float  # Price per share (0-1)
    ) -> Optional[Dict]:
        """
        Place an order.

        Args:
            contract_ticker: Contract ticker (e.g., "KXBTC-000")
            side: "yes" or "no"
            quantity: Number of shares
            price: Limit price (0-1)

        Returns:
            Order details (id, status, etc.)
        """
        body = {
            "ticker": contract_ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "order_type": "limit",
        }

        return self._request("POST", "/exchange/v2/orders", body)

    def get_orders(self) -> Optional[List[Dict]]:
        """Get all active orders."""
        result = self._request("GET", "/exchange/v2/orders")
        if result and "orders" in result:
            return result["orders"]
        return None

    def get_order(self, order_id: str) -> Optional[Dict]:
        """Get order details."""
        return self._request("GET", f"/exchange/v2/orders/{order_id}")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        result = self._request("DELETE", f"/exchange/v2/orders/{order_id}")
        return result is not None

    # ========================================================================
    # Position Methods
    # ========================================================================

    def get_positions(self) -> Optional[List[Dict]]:
        """Get all positions."""
        result = self._request("GET", "/exchange/v2/portfolio")
        if result and "positions" in result:
            return result["positions"]
        return None

    def get_position(self, contract_ticker: str) -> Optional[Dict]:
        """Get position details for a contract."""
        positions = self.get_positions()
        if positions:
            for pos in positions:
                if pos.get("ticker") == contract_ticker:
                    return pos
        return None

    def close_position(self, contract_ticker: str, quantity: int) -> Optional[Dict]:
        """
        Close a position by selling/buying opposite quantity.

        Args:
            contract_ticker: Contract ticker
            quantity: Quantity to close

        Returns:
            Order details
        """
        position = self.get_position(contract_ticker)
        if not position:
            logger.warning(f"No position found for {contract_ticker}")
            return None

        # Determine opposite side
        current_side = "yes" if position.get("yes_count", 0) > 0 else "no"
        close_side = "no" if current_side == "yes" else "yes"

        # Get current market price
        orderbook = self.get_orderbook(contract_ticker)
        if not orderbook:
            logger.error(f"Could not get orderbook for {contract_ticker}")
            return None

        # Use market price (ask for buy, bid for sell)
        if close_side == "yes":
            close_price = orderbook.get("yes_ask", 0.5)
        else:
            close_price = orderbook.get("no_ask", 0.5)

        return self.place_order(contract_ticker, close_side, quantity, close_price)

    # ========================================================================
    # Account Methods
    # ========================================================================

    def get_account(self) -> Optional[Dict]:
        """Get account details (balance, etc.)."""
        return self._request("GET", "/exchange/v2/accounts/me")

    def get_balance(self) -> Optional[float]:
        """Get account balance."""
        account = self.get_account()
        if account:
            return account.get("balance_cents", 0) / 100.0
        return None

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def health_check(self) -> bool:
        """Check if API is accessible."""
        try:
            markets = self.get_markets()
            return markets is not None
        except:
            return False

    def get_contract_price(
        self,
        contract_ticker: str,
        side: str = "yes"
    ) -> Optional[float]:
        """
        Get current contract price.

        Args:
            contract_ticker: Contract ticker
            side: "yes" or "no" (which side's price to get)

        Returns:
            Price (0-1), or None if unavailable
        """
        orderbook = self.get_orderbook(contract_ticker)
        if not orderbook:
            return None

        if side == "yes":
            # For YES, use the ask price (what you pay to buy YES)
            return orderbook.get("yes_ask")
        else:
            # For NO, use the ask price (what you pay to buy NO)
            return orderbook.get("no_ask")
