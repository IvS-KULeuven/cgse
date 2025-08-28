import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotificationEvent:
    event_type: str
    source_service: str
    data: dict
    timestamp: float
    correlation_id: Optional[str] = None

    def as_dict(self):
        return {
            "event_type": self.event_type,
            "source_service": self.source_service,
            "data": self.data,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id or str(uuid.uuid4()),
        }
