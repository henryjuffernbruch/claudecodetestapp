"""
SPECTER Reddit Ingestion - Collect engagement metrics from Reddit.
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Any

try:
    import praw
except ImportError:
    praw = None

from specter.storage.models import RawSignal
from specter.config import settings

logger = logging.getLogger(__name__)


class RedditCollector:
    """Collects engagement metrics from Reddit."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """Initialize Reddit API client."""
        if not praw:
            raise ImportError("praw not installed. Install with: pip install praw")

        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
        self.last_request_time = 0
        self.rate_limit_delay = 60 / settings.REDDIT_RATE_LIMIT_REQUESTS_PER_MIN

    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def collect(self, topic: str, subreddits: List[str]) -> RawSignal:
        """Collect Reddit metrics for a topic."""
        logger.info(f"Collecting Reddit metrics for {topic}")

        metrics = {
            "posts_count": 0,
            "comments_count": 0,
            "avg_upvote_ratio": 0.0,
            "top_post_score": 0,
            "unique_authors": set(),
        }

        try:
            for subreddit_name in subreddits:
                self._rate_limit()
                subreddit = self.reddit.subreddit(subreddit_name.replace("r/", ""))

                # Fetch recent posts
                posts = subreddit.new(limit=50)  # Last 50 posts
                post_count = 0
                upvote_ratio_sum = 0

                for post in posts:
                    post_count += 1
                    metrics["posts_count"] += 1
                    metrics["comments_count"] += post.num_comments
                    upvote_ratio_sum += post.upvote_ratio
                    metrics["unique_authors"].add(post.author.name if post.author else "deleted")

                    if post.score > metrics["top_post_score"]:
                        metrics["top_post_score"] = post.score

                if post_count > 0:
                    metrics["avg_upvote_ratio"] += upvote_ratio_sum / post_count

        except Exception as e:
            logger.error(f"Error collecting Reddit metrics for {topic}: {e}")
            # Return what we have so far

        # Convert set to count
        metrics["unique_authors_count"] = len(metrics["unique_authors"])
        del metrics["unique_authors"]

        # Normalize upvote ratio to 0-1 scale (already 0-1 from Reddit API)
        metrics["avg_upvote_ratio"] = min(1.0, max(0.0, metrics["avg_upvote_ratio"]))

        signal = RawSignal(
            topic=topic,
            platform="reddit",
            timestamp=datetime.utcnow(),
            metrics=metrics,
        )

        logger.info(f"Collected Reddit metrics: {metrics}")
        return signal


def create_reddit_collector(
    client_id: str = None,
    client_secret: str = None,
    user_agent: str = "SPECTER/1.0"
) -> RedditCollector:
    """Factory function to create Reddit collector with proper credentials."""
    if client_id is None or client_secret is None:
        from specter.config import secrets
        client_id = getattr(secrets, "REDDIT_CLIENT_ID", "")
        client_secret = getattr(secrets, "REDDIT_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("Reddit credentials not configured. Reddit collection disabled.")
        return None

    return RedditCollector(client_id, client_secret, user_agent)
