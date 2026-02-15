"""
SPECTER YouTube Ingestion - Collect engagement metrics from YouTube.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    build = None

from specter.storage.models import RawSignal
from specter.config import settings

logger = logging.getLogger(__name__)


class YouTubeCollector:
    """Collects engagement metrics from YouTube."""

    def __init__(self, api_key: str):
        """Initialize YouTube API client."""
        if not build:
            raise ImportError("google-api-python-client not installed.")

        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.quota_used_today = 0
        self.quota_reset_time = datetime.utcnow() + timedelta(days=1)
        self.last_request_time = 0

    def _check_quota(self, units_needed: int) -> bool:
        """Check if we have quota available."""
        # Reset quota if new day
        if datetime.utcnow() > self.quota_reset_time:
            self.quota_used_today = 0
            self.quota_reset_time = datetime.utcnow() + timedelta(days=1)

        if self.quota_used_today + units_needed > settings.YOUTUBE_QUOTA_PER_DAY:
            remaining = settings.YOUTUBE_QUOTA_PER_DAY - self.quota_used_today
            logger.warning(
                f"YouTube quota insufficient. Used: {self.quota_used_today}/"
                f"{settings.YOUTUBE_QUOTA_PER_DAY}. Needed: {units_needed}. Remaining: {remaining}"
            )
            return False
        return True

    def _rate_limit(self):
        """Rate limiting to avoid quota exhaustion."""
        min_interval = 0.5  # seconds between requests
        elapsed = time.time() - self.last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self.last_request_time = time.time()

    def collect(self, topic: str, search_query: str) -> RawSignal:
        """Collect YouTube metrics for a topic."""
        logger.info(f"Collecting YouTube metrics for {topic}: {search_query}")

        metrics = {
            "video_count": 0,
            "total_views": 0,
            "total_comments": 0,
            "avg_likes": 0.0,
            "search_query": search_query,
        }

        # Search for recent videos (last 24 hours)
        if not self._check_quota(settings.YOUTUBE_COST_PER_SEARCH):
            logger.warning(f"Skipping YouTube collection for {topic} due to quota limits")
            return RawSignal(
                topic=topic,
                platform="youtube",
                timestamp=datetime.utcnow(),
                metrics=metrics,
            )

        try:
            self._rate_limit()

            # Search for videos uploaded in last 24 hours
            published_after = (datetime.utcnow() - timedelta(hours=24)).isoformat() + "Z"

            search_response = self.youtube.search().list(
                q=search_query,
                part="snippet",
                type="video",
                maxResults=50,
                publishedAfter=published_after,
                order="relevance",
                safeSearch="none",
            ).execute()

            self.quota_used_today += settings.YOUTUBE_COST_PER_SEARCH

            video_ids = []
            for item in search_response.get("items", []):
                video_ids.append(item["id"]["videoId"])

            metrics["video_count"] = len(video_ids)

            # Get statistics for each video (if we have quota)
            if video_ids and self._check_quota(len(video_ids)):
                self._rate_limit()

                videos_response = self.youtube.videos().list(
                    part="statistics,snippet",
                    id=",".join(video_ids),
                ).execute()

                self.quota_used_today += len(video_ids)

                total_likes = 0
                like_count = 0

                for video in videos_response.get("items", []):
                    stats = video.get("statistics", {})
                    metrics["total_views"] += int(stats.get("viewCount", 0))
                    metrics["total_comments"] += int(stats.get("commentCount", 0))

                    like_count_video = int(stats.get("likeCount", 0))
                    if like_count_video > 0:
                        total_likes += like_count_video
                        like_count += 1

                if like_count > 0:
                    metrics["avg_likes"] = total_likes / like_count

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
        except Exception as e:
            logger.error(f"Error collecting YouTube metrics for {topic}: {e}")

        signal = RawSignal(
            topic=topic,
            platform="youtube",
            timestamp=datetime.utcnow(),
            metrics=metrics,
        )

        logger.info(f"Collected YouTube metrics: {metrics}")
        return signal


def create_youtube_collector(api_key: str = None) -> YouTubeCollector:
    """Factory function to create YouTube collector with proper credentials."""
    if api_key is None:
        from specter.config import secrets
        api_key = getattr(secrets, "YOUTUBE_API_KEY", "")

    if not api_key:
        logger.warning("YouTube API key not configured. YouTube collection disabled.")
        return None

    return YouTubeCollector(api_key)
