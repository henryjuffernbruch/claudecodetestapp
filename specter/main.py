"""
SPECTER Main - Core event loop orchestrating the full system.
Runs every 60 seconds: ingest → compute EI → store → classify → signal → execute.
"""

import logging
import logging.handlers
import time
import sys
import os
from datetime import datetime, timedelta
import signal as signal_handler

from specter.config import settings
from specter.ingestion.aggregator import create_aggregator
from specter.index.engine import EngagementIndexEngine
from specter.storage.timeseries_db import TimeseriesDB
from specter.storage.models import Classification
from specter.classifier.rules import RuleBasedClassifier
from specter.signals.generator import SignalGenerator
from specter.monitoring.alerts import AlertsManager

# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging():
    """Configure logging to file and console."""
    log_dir = settings.LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger("specter")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    # File handler (rotating)
    log_file = os.path.join(log_dir, "specter.log")
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# ============================================================================
# SPECTER System
# ============================================================================

class SPECTERSystem:
    """Main SPECTER system orchestrator."""

    def __init__(self):
        """Initialize SPECTER system."""
        self.logger = logging.getLogger("specter")
        self.running = False
        self.start_time = None
        self.loop_count = 0
        self.error_count = 0
        self.last_loop_time = None

        # Initialize components
        self.logger.info("=" * 80)
        self.logger.info("SPECTER System Initializing")
        self.logger.info("=" * 80)

        try:
            self.aggregator = create_aggregator()
            self.logger.info("✓ Ingestion aggregator initialized")

            self.ei_engine = EngagementIndexEngine()
            self.logger.info("✓ Engagement Index engine initialized")

            self.db = TimeseriesDB()
            self.logger.info("✓ Database initialized")

            # Phase 2 components
            self.classifier = RuleBasedClassifier()
            self.logger.info("✓ Classifier initialized")

            self.signal_generator = SignalGenerator()
            self.logger.info("✓ Signal generator initialized")

            self.alerts_manager = AlertsManager()
            self.logger.info("✓ Alerts manager initialized")

            # Verify collectors
            collector_status = self.aggregator.get_status()
            self.logger.info(f"Collector status: {collector_status}")

        except Exception as e:
            self.logger.error(f"Failed to initialize system: {e}")
            raise

        self.logger.info("=" * 80)
        self.logger.info("SPECTER System Ready")
        self.logger.info("=" * 80)

    def handle_shutdown(self, signum, frame):
        """Handle graceful shutdown."""
        self.logger.info("Shutdown signal received. Stopping...")
        self.running = False

    def run(self):
        """Run main event loop."""
        self.running = True
        self.start_time = datetime.utcnow()

        # Register signal handlers
        signal_handler.signal(signal_handler.SIGINT, self.handle_shutdown)
        signal_handler.signal(signal_handler.SIGTERM, self.handle_shutdown)

        self.logger.info("Starting main loop")

        while self.running:
            self.loop_count += 1
            loop_start = time.time()

            try:
                self._loop_iteration()
            except Exception as e:
                self.logger.error(f"Loop error: {e}", exc_info=True)
                self.error_count += 1

            # Sleep to maintain 60-second cadence
            elapsed = time.time() - loop_start
            sleep_time = max(0, settings.POLL_INTERVAL_SECONDS - elapsed)

            if sleep_time > 0:
                time.sleep(sleep_time)

            self.last_loop_time = time.time() - loop_start

        self._shutdown()

    def _loop_iteration(self):
        """Single iteration of the main loop."""
        current_time = datetime.utcnow()

        # ====================================================================
        # Step 1: INGEST - Collect data from all platforms
        # ====================================================================
        self.logger.debug("Step 1: Ingesting data...")
        signals_by_topic = self.aggregator.collect_all_topics()

        # ====================================================================
        # Step 2: COMPUTE - Run EI pipeline
        # ====================================================================
        self.logger.debug("Step 2: Computing engagement indices...")
        eis = self.ei_engine.compute_batch(signals_by_topic, current_time)

        # ====================================================================
        # Step 3: STORE - Log all data
        # ====================================================================
        self.logger.debug("Step 3: Storing to database...")

        stored_ei_count = 0
        stored_signal_count = 0

        for topic, ei in eis.items():
            if self.db.insert_engagement_index(ei):
                stored_ei_count += 1

        # Also store raw signals
        for topic, signals in signals_by_topic.items():
            for platform, signal in signals.items():
                if self.db.insert_raw_signal(signal):
                    stored_signal_count += 1

        self.logger.info(
            f"[Loop {self.loop_count}] Stored: {stored_ei_count} EI, "
            f"{stored_signal_count} raw signals. "
            f"Loop time: {self.last_loop_time:.2f}s"
        )

        # ====================================================================
        # Step 4: CLASSIFY - Decay pattern classification (Phase 2)
        # ====================================================================
        self.logger.debug("Step 4: Classifying attention decay patterns...")
        classifications = {}

        for topic, ei in eis.items():
            # Get EI history for classification window
            ei_history = self.ei_engine.get_history(topic, limit=30)
            if ei_history:
                ei_values = [ei_val for ei_val, _ in ei_history]
                archetype, confidence, features = self.classifier.classify(ei_values)

                classification = Classification(
                    topic=topic,
                    timestamp=current_time,
                    archetype=archetype,
                    confidence=confidence,
                    features=features,
                    metadata={"ei_window_size": len(ei_values)},
                )
                classifications[topic] = classification

                if self.db.insert_classification(classification):
                    stored_signal_count += 1

        # ====================================================================
        # Step 5: SIGNAL - Generate trading signals (Phase 2)
        # ====================================================================
        self.logger.debug("Step 5: Generating trading signals...")
        trade_signals = self.signal_generator.generate_signals_batch(eis)

        signal_count = len(trade_signals)
        for signal in trade_signals:
            try:
                self.alerts_manager.send_signal_alert(signal)
            except Exception as e:
                self.logger.error(f"Failed to send signal alert: {e}")

        # ====================================================================
        # Steps 6 & 7: EXECUTE & MONITOR (Phase 3+)
        # ====================================================================
        # Placeholder for future trade execution and monitoring

        self.logger.info(
            f"[Loop {self.loop_count}] Stored: {stored_ei_count} EI, "
            f"{stored_signal_count} signals, {signal_count} trade signals. "
            f"Loop time: {self.last_loop_time:.2f}s"
        )

    def _shutdown(self):
        """Perform shutdown operations."""
        uptime = datetime.utcnow() - self.start_time
        self.logger.info("=" * 80)
        self.logger.info("SPECTER System Shutdown")
        self.logger.info(f"Loops completed: {self.loop_count}")
        self.logger.info(f"Errors: {self.error_count}")
        self.logger.info(f"Uptime: {uptime}")
        self.logger.info(f"Database size: {self.db.get_db_size() / 1024:.1f} KB")

        perf = self.db.compute_performance()
        self.logger.info(f"Performance: {perf}")

        self.logger.info("=" * 80)


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Main entry point."""
    setup_logging()

    system = SPECTERSystem()
    system.run()


if __name__ == "__main__":
    main()
