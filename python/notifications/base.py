"""
Base notification models and channel interface.

Defines the common structure for all notification channels
(Telegram, Email, Desktop) used by BARQ's multi-channel alert system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Priority(Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    def score(self) -> int:
        return {"low": 0, "normal": 1, "high": 2, "urgent": 3}[self.value]


class Category(Enum):
    GENERAL = "general"
    JOB_MATCH = "job_match"
    APPLICATION = "application"
    CONTENT = "content"
    ANALYTICS = "analytics"
    ERROR = "error"
    SYSTEM = "system"


class Channel(Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"
    DESKTOP = "desktop"
    ALL = "all"


@dataclass
class NotificationEvent:
    """A notification event to be dispatched through channels."""

    title: str
    body: str
    priority: Priority = Priority.NORMAL
    category: Category = Category.GENERAL
    channel: Channel = Channel.ALL
    related_entity_type: Optional[str] = None
    related_entity_id: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dict for database insertion."""
        return {
            "channel": self.channel.value,
            "title": self.title,
            "body": self.body,
            "priority": self.priority.value,
            "category": self.category.value,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to a serializable dict for API responses."""
        return {
            "title": self.title,
            "body": self.body,
            "priority": self.priority.value,
            "category": self.category.value,
            "channel": self.channel.value,
            "related_entity_type": self.related_entity_type,
            "related_entity_id": self.related_entity_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class NotificationResult:
    """Result of sending a notification through a channel."""

    success: bool
    channel: Channel
    message: str = ""
    error: Optional[str] = None


class NotificationChannel(ABC):
    """Abstract base class for notification channels."""

    @abstractmethod
    async def send(self, event: NotificationEvent) -> NotificationResult:
        """Send a notification through this channel."""
        ...

    @abstractmethod
    async def is_enabled(self) -> bool:
        """Check if this channel is configured and ready."""
        ...

    @property
    @abstractmethod
    def channel_type(self) -> Channel:
        """Return the channel type enum."""
        ...
