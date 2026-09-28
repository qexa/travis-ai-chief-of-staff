from __future__ import annotations

from ..settings import get_settings
from .base import CalendarBackend, Event

_backend: CalendarBackend | None = None


def get_calendar() -> CalendarBackend:
    global _backend
    if _backend is None:
        kind = get_settings().calendar_backend
        if kind == "google":
            from .google import GoogleCalendar
            _backend = GoogleCalendar()
        elif kind == "demo":
            from .demo import DemoCalendar
            _backend = DemoCalendar()
        else:
            raise ValueError(f"Unknown CALENDAR_BACKEND={kind!r} (use demo or google; see docs/05)")
    return _backend


def reset_calendar() -> None:
    global _backend
    _backend = None


__all__ = ["CalendarBackend", "Event", "get_calendar", "reset_calendar"]
