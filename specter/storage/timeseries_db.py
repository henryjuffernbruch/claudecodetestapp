"""
SPECTER Timeseries Database - SQLite storage for all system data.
"""

import os
import json
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import List, Optional, Dict, Any

from specter.storage.models import (
    RawSignal, EngagementIndex, Classification, Trade, SystemStatus
)
from specter.config import settings


class TimeseriesDB:
    """SQLite database for storing all SPECTER data."""

    def __init__(self, db_path: str = None):
        """Initialize database."""
        self.db_path = db_path or settings.DB_PATH
        self._ensure_directory()
        self._init_schema()

    def _ensure_directory(self):
        """Create database directory if needed."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        """Get database connection context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Raw signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(topic, platform, timestamp)
                )
            """)

            # Engagement index table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS engagement_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    raw_ei REAL NOT NULL,
                    smoothed_ei REAL NOT NULL,
                    components TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(topic, timestamp)
                )
            """)

            # Classifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    archetype TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    features TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(topic, timestamp)
                )
            """)

            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    venue TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_size REAL NOT NULL,
                    exit_price REAL,
                    exit_size REAL,
                    pnl REAL,
                    signal_confidence REAL NOT NULL,
                    signal_archetype TEXT NOT NULL,
                    opened_at TEXT NOT NULL,
                    closed_at TEXT,
                    status TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indices for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ei_topic_timestamp
                ON engagement_index(topic, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_class_topic_timestamp
                ON classifications(topic, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_opened_at
                ON trades(opened_at)
            """)

            conn.commit()

    # ========================================================================
    # Raw Signals
    # ========================================================================

    def insert_raw_signal(self, signal: RawSignal) -> bool:
        """Insert a raw signal. Returns True if inserted, False if duplicate."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO raw_signals (topic, platform, timestamp, metrics)
                    VALUES (?, ?, ?, ?)
                """, (
                    signal.topic,
                    signal.platform,
                    signal.timestamp.isoformat(),
                    json.dumps(signal.metrics),
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # Duplicate

    def get_raw_signals(
        self,
        topic: str,
        platform: Optional[str] = None,
        limit: int = 100
    ) -> List[RawSignal]:
        """Retrieve raw signals for a topic."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if platform:
                cursor.execute("""
                    SELECT * FROM raw_signals
                    WHERE topic = ? AND platform = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (topic, platform, limit))
            else:
                cursor.execute("""
                    SELECT * FROM raw_signals
                    WHERE topic = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (topic, limit))

            rows = cursor.fetchall()
            signals = []
            for row in rows:
                signal = RawSignal(
                    topic=row["topic"],
                    platform=row["platform"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    metrics=json.loads(row["metrics"]),
                )
                signals.append(signal)
            return signals

    # ========================================================================
    # Engagement Index
    # ========================================================================

    def insert_engagement_index(self, ei: EngagementIndex) -> bool:
        """Insert an engagement index. Returns True if inserted."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO engagement_index
                    (topic, timestamp, raw_ei, smoothed_ei, components, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    ei.topic,
                    ei.timestamp.isoformat(),
                    ei.raw_ei,
                    ei.smoothed_ei,
                    json.dumps(ei.components),
                    json.dumps(ei.metadata),
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_engagement_index(
        self,
        topic: str,
        limit: int = 100
    ) -> List[EngagementIndex]:
        """Retrieve engagement index for a topic."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM engagement_index
                WHERE topic = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (topic, limit))

            rows = cursor.fetchall()
            indices = []
            for row in rows:
                ei = EngagementIndex(
                    topic=row["topic"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    raw_ei=row["raw_ei"],
                    smoothed_ei=row["smoothed_ei"],
                    components=json.loads(row["components"]),
                    metadata=json.loads(row["metadata"]),
                )
                indices.append(ei)
            return indices

    def get_latest_ei(self, topic: str) -> Optional[EngagementIndex]:
        """Get most recent EI for a topic."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM engagement_index
                WHERE topic = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (topic,))

            row = cursor.fetchone()
            if not row:
                return None

            return EngagementIndex(
                topic=row["topic"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                raw_ei=row["raw_ei"],
                smoothed_ei=row["smoothed_ei"],
                components=json.loads(row["components"]),
                metadata=json.loads(row["metadata"]),
            )

    # ========================================================================
    # Classifications
    # ========================================================================

    def insert_classification(self, classification: Classification) -> bool:
        """Insert a classification."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO classifications
                    (topic, timestamp, archetype, confidence, features, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    classification.topic,
                    classification.timestamp.isoformat(),
                    classification.archetype,
                    classification.confidence,
                    json.dumps(classification.features),
                    json.dumps(classification.metadata),
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def get_classifications(
        self,
        topic: str,
        limit: int = 100
    ) -> List[Classification]:
        """Retrieve classifications for a topic."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM classifications
                WHERE topic = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (topic, limit))

            rows = cursor.fetchall()
            classifications = []
            for row in rows:
                cls = Classification(
                    topic=row["topic"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    archetype=row["archetype"],
                    confidence=row["confidence"],
                    features=json.loads(row["features"]),
                    metadata=json.loads(row["metadata"]),
                )
                classifications.append(cls)
            return classifications

    # ========================================================================
    # Trades
    # ========================================================================

    def insert_trade(self, trade: Trade) -> bool:
        """Insert a trade."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO trades
                    (id, topic, venue, direction, entry_price, entry_size,
                     exit_price, exit_size, pnl, signal_confidence,
                     signal_archetype, opened_at, closed_at, status, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trade.id,
                    trade.topic,
                    trade.venue,
                    trade.direction,
                    trade.entry_price,
                    trade.entry_size,
                    trade.exit_price,
                    trade.exit_size,
                    trade.pnl,
                    trade.signal_confidence,
                    trade.signal_archetype,
                    trade.opened_at.isoformat(),
                    trade.closed_at.isoformat() if trade.closed_at else None,
                    trade.status,
                    trade.notes,
                ))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False

    def update_trade(self, trade: Trade) -> bool:
        """Update an existing trade."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE trades
                SET exit_price = ?, exit_size = ?, pnl = ?, closed_at = ?, status = ?, notes = ?
                WHERE id = ?
            """, (
                trade.exit_price,
                trade.exit_size,
                trade.pnl,
                trade.closed_at.isoformat() if trade.closed_at else None,
                trade.status,
                trade.notes,
                trade.id,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def get_trades(
        self,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Trade]:
        """Retrieve trades with optional filtering."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM trades WHERE 1=1"
            params = []

            if topic:
                query += " AND topic = ?"
                params.append(topic)
            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY opened_at DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            trades = []
            for row in rows:
                trade = Trade(
                    id=row["id"],
                    topic=row["topic"],
                    venue=row["venue"],
                    direction=row["direction"],
                    entry_price=row["entry_price"],
                    entry_size=row["entry_size"],
                    exit_price=row["exit_price"],
                    exit_size=row["exit_size"],
                    pnl=row["pnl"],
                    signal_confidence=row["signal_confidence"],
                    signal_archetype=row["signal_archetype"],
                    opened_at=datetime.fromisoformat(row["opened_at"]),
                    closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
                    status=row["status"],
                    notes=row["notes"],
                )
                trades.append(trade)
            return trades

    def get_open_trades(self) -> List[Trade]:
        """Get all currently open trades."""
        return self.get_trades(status="open")

    # ========================================================================
    # Performance Metrics
    # ========================================================================

    def compute_performance(self) -> Dict[str, Any]:
        """Compute overall P&L and performance metrics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Total P&L
            cursor.execute("SELECT SUM(pnl) as total_pnl FROM trades WHERE pnl IS NOT NULL")
            total_pnl = cursor.fetchone()["total_pnl"] or 0.0

            # Daily P&L
            cursor.execute("""
                SELECT SUM(pnl) as daily_pnl FROM trades
                WHERE pnl IS NOT NULL AND DATE(closed_at) = DATE('now')
            """)
            daily_pnl = cursor.fetchone()["daily_pnl"] or 0.0

            # Win rate
            cursor.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
                FROM trades
                WHERE pnl IS NOT NULL
            """)
            result = cursor.fetchone()
            total_trades = result["total_trades"]
            wins = result["wins"] or 0
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

            # Open positions
            cursor.execute("SELECT COUNT(*) as count FROM trades WHERE status = 'open'")
            open_positions = cursor.fetchone()["count"]

            return {
                "total_pnl": total_pnl,
                "daily_pnl": daily_pnl,
                "total_trades": total_trades,
                "win_rate": win_rate,
                "open_positions": open_positions,
            }

    # ========================================================================
    # Cleanup & Admin
    # ========================================================================

    def clear_all(self):
        """WARNING: Delete all data. For testing only."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM raw_signals")
            cursor.execute("DELETE FROM engagement_index")
            cursor.execute("DELETE FROM classifications")
            cursor.execute("DELETE FROM trades")
            conn.commit()

    def get_db_size(self) -> int:
        """Get database file size in bytes."""
        return os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
