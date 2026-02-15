"""
SPECTER Ingestion Aggregator - Orchestrate data collection from all platforms.
"""

import logging
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional

from specter.storage.models import RawSignal
from specter.config import settings
from specter.ingestion import twitter, reddit, youtube

logger = logging.getLogger(__name__)


class IngestionAggregator:
    """Orchestrates data collection from Twitter, Reddit, and YouTube."""

    def __init__(self):
        """Initialize all collectors."""
        self.twitter_collector = None
        self.reddit_collector = None
        self.youtube_collector = None

        self._init_collectors()

    def _init_collectors(self):
        """Initialize collectors with credentials."""
        # Twitter
        if settings.TWITTER_ENABLED:
            try:
                self.twitter_collector = twitter.create_twitter_collector()
            except Exception as e:
                logger.error(f"Failed to initialize Twitter collector: {e}")

        # Reddit
        if settings.REDDIT_ENABLED:
            try:
                self.reddit_collector = reddit.create_reddit_collector()
            except Exception as e:
                logger.error(f"Failed to initialize Reddit collector: {e}")

        # YouTube
        if settings.YOUTUBE_ENABLED:
            try:
                self.youtube_collector = youtube.create_youtube_collector()
            except Exception as e:
                logger.error(f"Failed to initialize YouTube collector: {e}")

        if not any([self.twitter_collector, self.reddit_collector, self.youtube_collector]):
            logger.warning("No collectors initialized. Check credentials in config/secrets.py")

    def collect_for_topic(self, topic: str) -> Dict[str, RawSignal]:
        """Collect data from all platforms for a single topic."""
        logger.info(f"Collecting data for topic: {topic}")

        if topic not in settings.TRACKED_TOPICS:
            logger.error(f"Topic {topic} not in TRACKED_TOPICS")
            return {}

        topic_config = settings.TRACKED_TOPICS[topic]
        signals = {}

        # Collect from Twitter
        if self.twitter_collector and topic_config.get("keywords_twitter"):
            try:
                signal = self.twitter_collector.collect(
                    topic,
                    topic_config["keywords_twitter"]
                )
                signals["twitter"] = signal
            except Exception as e:
                logger.error(f"Twitter collection failed for {topic}: {e}")

        # Collect from Reddit
        if self.reddit_collector and topic_config.get("subreddits"):
            try:
                signal = self.reddit_collector.collect(
                    topic,
                    topic_config["subreddits"]
                )
                signals["reddit"] = signal
            except Exception as e:
                logger.error(f"Reddit collection failed for {topic}: {e}")

        # Collect from YouTube
        if self.youtube_collector and topic_config.get("youtube_search"):
            try:
                signal = self.youtube_collector.collect(
                    topic,
                    topic_config["youtube_search"]
                )
                signals["youtube"] = signal
            except Exception as e:
                logger.error(f"YouTube collection failed for {topic}: {e}")

        return signals

    def collect_all_topics(self) -> Dict[str, Dict[str, RawSignal]]:
        """Collect data from all platforms for all tracked topics."""
        logger.info(f"Starting collection for {len(settings.TRACKED_TOPICS)} topics")

        all_signals = {}

        # Collect sequentially (simple, avoids rate limiting issues)
        for topic in settings.TRACKED_TOPICS:
            try:
                signals = self.collect_for_topic(topic)
                all_signals[topic] = signals
            except Exception as e:
                logger.error(f"Failed to collect data for {topic}: {e}")
                all_signals[topic] = {}

        logger.info(f"Collection complete. Topics with data: {len([t for t in all_signals if all_signals[t]])}/{len(settings.TRACKED_TOPICS)}")
        return all_signals

    def get_status(self) -> Dict[str, bool]:
        """Get status of all collectors."""
        return {
            "twitter": self.twitter_collector is not None,
            "reddit": self.reddit_collector is not None,
            "youtube": self.youtube_collector is not None,
        }


def create_aggregator() -> IngestionAggregator:
    """Factory function to create ingestion aggregator."""
    return IngestionAggregator()
