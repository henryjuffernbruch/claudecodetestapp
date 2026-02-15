"""
SPECTER Kalshi Mapper - Map attention topics to Kalshi trading contracts.
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# Topic to Contract Mappings
# ============================================================================

TOPIC_CONTRACT_MAP = {
    "BTC": {
        "venue": "kalshi",
        "contract_family": "KXBTC",
        "description": "Bitcoin 15-minute contracts",
        "direction_logic": "positive_correlation",  # Attention up → price likely up
        "contract_type": "crypto_15min",
        "active": True,
    },
    "ETH": {
        "venue": "kalshi",
        "contract_family": "KXETH",
        "description": "Ethereum 15-minute contracts",
        "direction_logic": "positive_correlation",
        "contract_type": "crypto_15min",
        "active": True,
    },
    "SOL": {
        "venue": "kalshi",
        "contract_family": "KXSOL",
        "description": "Solana 15-minute contracts",
        "direction_logic": "positive_correlation",
        "contract_type": "crypto_15min",
        "active": True,
    },
    "TRUMP": {
        "venue": "kalshi",
        "contract_family": "TRUMP",
        "description": "Trump-related prediction contracts",
        "direction_logic": "positive_correlation",
        "contract_type": "politics",
        "active": False,  # Will activate when contract available
    },
    "AI_HYPE": {
        "venue": "trendle",  # Future venue
        "contract_family": "AI",
        "description": "AI narrative attention index",
        "direction_logic": "positive_correlation",
        "contract_type": "narrative",
        "active": False,
    },
}

# ============================================================================
# Trendle Mappings (Future)
# ============================================================================

TRENDLE_TOPIC_MAP = {
    # Will be populated when Trendle API becomes available
    # Format: "TOPIC": {
    #     "market_id": "...",
    #     "direction_logic": "positive_correlation",
    # }
}


# ============================================================================
# Kalshi Mapper Class
# ============================================================================

class KalshiMapper:
    """Maps attention topics to Kalshi contracts."""

    def __init__(self):
        """Initialize mapper."""
        self.topic_map = TOPIC_CONTRACT_MAP

    def get_contract_for_topic(self, topic: str) -> Optional[Dict]:
        """
        Get contract mapping for a topic.

        Returns:
            {
                "venue": "kalshi" | "trendle",
                "contract_family": "KXBTC" | etc,
                "description": "...",
                "direction_logic": "positive_correlation" | "negative_correlation",
                "contract_type": "crypto_15min" | "politics" | etc,
                "active": bool,
            }
            or None if topic not mapped
        """
        return self.topic_map.get(topic)

    def is_tradeable(self, topic: str) -> bool:
        """Check if topic has an active tradeable contract."""
        mapping = self.get_contract_for_topic(topic)
        if not mapping:
            return False

        # Check if contract is active and venue is available
        if not mapping.get("active"):
            return False

        venue = mapping.get("venue")
        if venue == "kalshi":
            return True
        elif venue == "trendle":
            # Trendle not available yet
            return False

        return False

    def get_direction(self, topic: str, divergence: float) -> Optional[str]:
        """
        Get trading direction for a topic based on divergence.

        Args:
            topic: Topic name
            divergence: Divergence value (positive = EI rising faster than price)

        Returns:
            "long" or "short" or None
        """
        mapping = self.get_contract_for_topic(topic)
        if not mapping:
            return None

        direction_logic = mapping.get("direction_logic")

        if direction_logic == "positive_correlation":
            # Positive divergence (EI rising faster) = expect price to rise = LONG
            # Negative divergence (EI falling faster) = expect price to fall = SHORT
            if divergence > 0:
                return "long"
            elif divergence < 0:
                return "short"
        elif direction_logic == "negative_correlation":
            # Inverted logic
            if divergence > 0:
                return "short"
            elif divergence < 0:
                return "long"

        return None

    def get_active_topics(self) -> list:
        """Get list of topics with active contracts."""
        return [
            topic for topic, mapping in self.topic_map.items()
            if mapping.get("active") and mapping.get("venue") == "kalshi"
        ]

    def get_tradeable_topics(self) -> list:
        """Get list of topics that are currently tradeable."""
        return [topic for topic in self.topic_map if self.is_tradeable(topic)]

    def add_topic(self, topic: str, mapping: Dict):
        """Add a new topic mapping."""
        self.topic_map[topic] = mapping
        logger.info(f"Added topic mapping: {topic} -> {mapping.get('contract_family')}")

    def update_topic(self, topic: str, **kwargs):
        """Update a topic mapping."""
        if topic not in self.topic_map:
            logger.warning(f"Topic {topic} not found in mapper")
            return

        self.topic_map[topic].update(kwargs)
        logger.info(f"Updated topic mapping: {topic}")


# ============================================================================
# Module-level functions
# ============================================================================

_mapper_instance = None


def get_mapper() -> KalshiMapper:
    """Get global mapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = KalshiMapper()
    return _mapper_instance


def is_topic_tradeable(topic: str) -> bool:
    """Check if topic is tradeable."""
    return get_mapper().is_tradeable(topic)


def get_contract_family(topic: str) -> Optional[str]:
    """Get contract family for a topic."""
    mapping = get_mapper().get_contract_for_topic(topic)
    return mapping.get("contract_family") if mapping else None
