"""Calendar backend interface. Implement these five methods to add Outlook, CalDAV, etc."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Event:
    id: str
    title: str
    start: datetime
    end: datetime
    attendees: list[dict[str, Any]] = field(default_factory=list)  # [{name, email, phone}]
    location: str = ""
    notes: str = ""
    kind: str = "meeting"  # meeting | travel | focus | personal

    def attendee_matches(self, name: str = "", phone: str = "", email: str = "") -> bool:
        from ..profile import normalize_phone

        for a in self.attendees:
            if phone and normalize_phone(a.get("phone")) == normalize_phone(phone):
                return True
            if email and (a.get("email") or "").lower() == email.lower():
                return True
            if name and name.lower() in (a.get("name") or "").lower():
                return True
        return bool(name and name.lower() in self.title.lower())


class CalendarBackend(ABC):
    @abstractmethod
    def list_events(self, start: datetime, end: datetime) -> list[Event]: ...

    @abstractmethod
    def get_event(self, event_id: str) -> Event | None: ...

    @abstractmethod
    def create_event(self, title: str, start: datetime, end: datetime, attendees: list[dict[str, Any]],
                     location: str = "", notes: str = "", kind: str = "meeting") -> Event: ...

    @abstractmethod
    def move_event(self, event_id: str, start: datetime, end: datetime) -> Event: ...

    @abstractmethod
    def delete_event(self, event_id: str) -> None: ...
