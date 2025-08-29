import time
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class NotificationEvent:
    event_type: str
    source_service: str
    data: dict
    timestamp: float | None = None
    correlation_id: str | None = None

    def __post_init__(self):
        if self.correlation_id is None:
            object.__setattr__(self, "correlation_id", str(uuid.uuid4()))

        if self.timestamp is None:
            object.__setattr__(self, "timestamp", time.time())

    def as_dict(self):
        return {
            "event_type": self.event_type,
            "source_service": self.source_service,
            "data": self.data,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id,
        }
