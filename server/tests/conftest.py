import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["TRAVIS_SCHEDULER"] = "false"
for k in ("TWILIO_ACCOUNT_SID", "SMTP_HOST", "ANTHROPIC_API_KEY", "VAPI_WEBHOOK_SECRET", "TRAVIS_ADMIN_TOKEN"):
    os.environ[k] = ""
os.environ["CALENDAR_BACKEND"] = "demo"


def next_monday() -> date:
    d = date.today() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Fresh DB + seeded demo day on a fixed Monday. Returns helpers."""
    monkeypatch.setenv("TRAVIS_DB", str(tmp_path / "t.db"))
    from travis import db, knowledge, settings, tools
    from travis.calendar import reset_calendar
    settings.reset_settings()
    db.reset_connection()
    reset_calendar()
    knowledge.reset_index()
    tools.CALL_STATE.clear()
    from travis.demo_data import seed
    from travis.profile import get_profile
    p = get_profile()
    monday = next_monday()
    ids = seed(datetime.combine(monday, time(6, 0), p.tz))

    def at(hh: int, mm: int = 0, day: date | None = None):
        monkeypatch.setenv("TRAVIS_FAKE_NOW", datetime.combine(day or monday, time(hh, mm)).isoformat())

    at(9, 30)
    return {"ids": ids, "monday": monday, "at": at, "profile": p}


@pytest.fixture()
def client(env):
    from fastapi.testclient import TestClient
    from travis.main import app
    return TestClient(app)
