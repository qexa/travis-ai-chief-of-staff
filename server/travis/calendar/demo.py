"""Local SQLite calendar so the whole system runs with no Google account."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from .. import db
from .base import CalendarBackend, Event


def _row_to_event(r: dict[str, Any]) -> Event:
    return Event(
        id=r["id"], title=r["title"],
        start=datetime.fromisoformat(r["start"]), end=datetime.fromisoformat(r["end"]),
        attendees=json.loads(r["attendees"] or "[]"), location=r["location"] or "",
        notes=r["notes"] or "", kind=r["kind"] or "meeting",
    )


class DemoCalendar(CalendarBackend):
    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        rows = db.query(
            "SELECT * FROM events WHERE status = 'confirmed' ORDER BY start",
        )
        # Compare as datetimes (stored strings may carry different offsets).
        events = [_row_to_event(r) for r in rows]
        return [e for e in events if e.end > start and e.start < end]

    def get_event(self, event_id: str) -> Event | None:
        r = db.one("SELECT * FROM events WHERE id = ? AND status = 'confirmed'", (event_id,))
        return _row_to_event(r) if r else None

    def create_event(self, title, start, end, attendees, location="", notes="", kind="meeting") -> Event:
        eid = "evt_" + uuid.uuid4().hex[:10]
        db.execute(
            "INSERT INTO events (id, title, start, end, attendees, location, notes, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (eid, title, start.isoformat(), end.isoformat(), json.dumps(attendees), location, notes, kind),
        )
        return self.get_event(eid)  # type: ignore[return-value]

    def move_event(self, event_id, start, end) -> Event:
        db.execute("UPDATE events SET start = ?, end = ? WHERE id = ?", (start.isoformat(), end.isoformat(), event_id))
        ev = self.get_event(event_id)
        if not ev:
            raise KeyError(event_id)
        return ev

    def delete_event(self, event_id) -> None:
        db.execute("UPDATE events SET status = 'cancelled' WHERE id = ?", (event_id,))
