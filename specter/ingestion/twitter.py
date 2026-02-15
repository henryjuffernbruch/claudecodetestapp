"""
SPECTER Twitter/X Ingestion - Collect engagement metrics from Twitter/X via snscrape.
Uses snscrape as a fallback method (no direct API required).
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

try:
    import snscrape.modules.twitter as sntwitter
except ImportError:
    sntwitter = None

from specter.storage.models import RawSignal
from specter.config import settings

logger = logging.getLogger(__name__)


class TwitterCollector:
    """Collects engagement metrics from Twitter/X via snscrape."""

    def __init__(self):
        """Initialize Twitter collector."""
        if not sntwitter:
            raise ImportError("snscrape not installed. Install with: pip install snscrape")
        self.last_request_time = 0
        self.rate_limit_delay = 60 / settings.TWITTER_RATE_LIMIT_REQUESTS_PER_MIN

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def collect(self, topic: str, keywords: List[str]) -> RawSignal:
        """Collect Twitter metrics for a topic."""
        logger.info(f"Collecting Twitter metrics for {topic}")

        metrics = {
            "tweet_count": 0,
            "reply_count": 0,
            "retweet_count": 0,
            "like_count": 0,
            "unique_authors": 0,
        }

        try:
            # Search for recent tweets (last 24 hours)
            since_date = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d")

            # Build search query
            query_parts = keywords + ["lang:en", f"since:{since_date}"]
            search_query = " OR ".join(f'"{kw}"' if " " in kw else kw for kw in keywords)
            search_query += f" -is:retweet lang:en since:{since_date}"

            logger.debug(f"Twitter search query: {search_query}")

            self._rate_limit()

            unique_authors = set()
            tweet_batch = []

            # Scrape tweets (limit to 500 per topic to avoid rate limit)
            for i, tweet in enumerate(sntwitter.TwitterSearchScraper(search_query).get_items()):
                if i >= 500:  # Max tweets to scrape
                    break

                tweet_batch.append(tweet)
                unique_authors.add(tweet.user.username)

                metrics["tweet_count"] += 1
                metrics["reply_count"] += tweet.replyCount or 0
                metrics["retweet_count"] += tweet.retweetCount or 0
                metrics["like_count"] += tweet.likeCount or 0

            metrics["unique_authors"] = len(unique_authors)

            # Rate limit after scraping
            time.sleep(1.0)
            self.last_request_time = time.time()

        except Exception as e:
            logger.error(f"Error collecting Twitter metrics for {topic}: {e}")
            # Return what we have

        signal = RawSignal(
            topic=topic,
            platform="twitter",
            timestamp=datetime.utcnow(),
            metrics=metrics,
        )

        logger.info(f"Collected Twitter metrics: {metrics}")
        return signal


def create_twitter_collector() -> TwitterCollector:
    """Factory function to create Twitter collector."""
    try:
        return TwitterCollector()
    except ImportError:
        logger.warning("snscrape not installed. Twitter collection disabled.")
        return None
