"""Google Calendar backend (REST + OAuth refresh token, no Google SDK needed).

Setup: docs/02-build-guide.md, Phase 5. You need a Google Cloud OAuth client
(Desktop or Web) with the scope https://www.googleapis.com/auth/calendar and a
refresh token for the executive's account (scripts/google_oauth.py gets one).
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx

from ..settings import get_settings
from .base import CalendarBackend, Event

API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleCalendar(CalendarBackend):
    def __init__(self) -> None:
        s = get_settings()
        self.cal_id = s.google_calendar_id
        self._token: str | None = None
        self._token_exp = 0.0
        self._client = httpx.Client(timeout=10)

    # ── auth ────────────────────────────────────────────────────────────────
    def _auth(self) -> dict[str, str]:
        if not self._token or time.time() > self._token_exp - 60:
            s = get_settings()
            r = self._client.post(TOKEN_URL, data={
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "refresh_token": s.google_refresh_token,
                "grant_type": "refresh_token",
            })
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_exp = time.time() + int(body.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._token}"}

    # ── mapping ─────────────────────────────────────────────────────────────
    @staticmethod
    def _to_event(item: dict[str, Any]) -> Event | None:
        s, e = item.get("start", {}), item.get("end", {})
        if "dateTime" not in s:  # all-day events: treat as not blocking meetings, but keep travel
            return None
        ext = item.get("extendedProperties", {}).get("private", {})
        return Event(
            id=item["id"], title=item.get("summary", "(busy)"),
            start=datetime.fromisoformat(s["dateTime"].replace("Z", "+00:00")),
            end=datetime.fromisoformat(e["dateTime"].replace("Z", "+00:00")),
            attendees=[{"name": a.get("displayName", ""), "email": a.get("email", ""), "phone": ext.get("phone", "")}
                       for a in item.get("attendees", []) if not a.get("self")],
            location=item.get("location", ""), notes=item.get("description", ""),
            kind=ext.get("travis_kind", "travel" if "flight" in item.get("summary", "").lower() else "meeting"),
        )

    # ── interface ───────────────────────────────────────────────────────────
    def list_events(self, start: datetime, end: datetime) -> list[Event]:
        r = self._client.get(f"{API}/calendars/{self.cal_id}/events", headers=self._auth(), params={
            "timeMin": start.isoformat(), "timeMax": end.isoformat(),
            "singleEvents": "true", "orderBy": "startTime", "maxResults": 250,
        })
        r.raise_for_status()
        out = []
        for item in r.json().get("items", []):
            if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
                continue
            ev = self._to_event(item)
            if ev:
                out.append(ev)
        return out

    def get_event(self, event_id: str) -> Event | None:
        r = self._client.get(f"{API}/calendars/{self.cal_id}/events/{event_id}", headers=self._auth())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return self._to_event(r.json())

    def create_event(self, title, start, end, attendees, location="", notes="", kind="meeting") -> Event:
        body = {
            "summary": title, "location": location, "description": notes,
            "start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()},
            "attendees": [{"email": a["email"], "displayName": a.get("name", "")} for a in attendees if a.get("email")],
            "extendedProperties": {"private": {"travis_kind": kind, "phone": (attendees[0].get("phone", "") if attendees else "")}},
        }
        r = self._client.post(f"{API}/calendars/{self.cal_id}/events", headers=self._auth(),
                              params={"sendUpdates": "all"}, json=body)
        r.raise_for_status()
        return self._to_event(r.json())  # type: ignore[return-value]

    def move_event(self, event_id, start, end) -> Event:
        r = self._client.patch(f"{API}/calendars/{self.cal_id}/events/{event_id}", headers=self._auth(),
                               params={"sendUpdates": "all"},
                               json={"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}})
        r.raise_for_status()
        return self._to_event(r.json())  # type: ignore[return-value]

    def delete_event(self, event_id) -> None:
        r = self._client.delete(f"{API}/calendars/{self.cal_id}/events/{event_id}", headers=self._auth(),
                                params={"sendUpdates": "all"})
        if r.status_code not in (200, 204, 404, 410):
            r.raise_for_status()
