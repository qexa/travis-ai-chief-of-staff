"""Fictional demo data for Jordan Hale (see config/executive.example.yaml).

Seeds a realistic day relative to `now`, so demos and tests always have a
board meeting to be "in", meetings to move, overnight calls, and spam to block.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from . import db
from .calendar import get_calendar
from .profile import get_profile


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def seed(now: datetime | None = None, wipe: bool = True) -> dict:
    p = get_profile()
    tz = p.tz
    now = (now or p.now()).astimezone(tz)
    if wipe:
        for t in ("events", "calls", "messages", "memories", "followups", "actions", "outbox", "contacts", "kv"):
            db.execute(f"DELETE FROM {t}")
    cal = get_calendar()
    today = _next_weekday(now.date())
    d1 = _next_weekday(today + timedelta(days=1))
    at = lambda d, h, m=0: datetime.combine(d, time(h, m), tz)  # noqa: E731

    ev = {}
    ev["staff"] = cal.create_event("Leadership staff meeting", at(today, 8, 30), at(today, 9, 15),
                                   [{"name": "Exec team"}])
    ev["priya"] = cal.create_event("Priya Nair (Crestline Freight) / Jordan: Q4 capacity", at(today, 10), at(today, 10, 30),
                                   [{"name": "Priya Nair", "email": "priya@crestline.example", "phone": "+16155550301"}])
    ev["board"] = cal.create_event("Board meeting", at(today, 13), at(today, 15),
                                   [{"name": "Board"}], location="Boardroom")
    ev["okafor"] = cal.create_event("David Okafor / Jordan: renewal", at(today, 15, 30), at(today, 16),
                                    [{"name": "David Okafor", "phone": "+16155550201"}])
    ev["flight"] = cal.create_event("Flight BNA → LGA", at(d1, 7), at(d1, 9, 30), [], kind="travel")
    ev["ny_dinner"] = cal.create_event("Dinner: Harbor Point partners", at(d1, 18, 30), at(d1, 20, 30),
                                       [{"name": "Catherine Blake", "phone": "+16155550200"}])

    # Known contacts
    db.upsert_contact("Priya Nair", "+16155550301", "Crestline Freight", tier="known", email="priya@crestline.example")
    db.upsert_contact("Tom Becker", "+16155550302", "Becker & Stone LLP", tier="known")
    db.upsert_contact("Robocaller", "+18885550999", "", tier="spam")

    # Overnight activity (for the briefing)
    last_night = datetime.combine(today - timedelta(days=1), time(19, 0), tz).astimezone(timezone.utc)
    rows = [
        ("demo-c1", "+16155550302", "Tom Becker", "Becker & Stone LLP", "known", "Lease amendment needs signature by Friday", "high", "message"),
        ("demo-c2", "+16155550400", "Alicia Moreno", "Ridgeview Partners", "new_opportunity", "Referred by David Okafor; wants to discuss a logistics partnership", "normal", "booked"),
        ("demo-c3", "+18885550999", "Robocaller", "", "spam", "Extended warranty", "low", "blocked"),
        ("demo-c4", "+18885550998", "Unknown", "", "spam", "Google listing", "low", "blocked"),
        ("demo-c5", "+16155550500", "Kevin Pratt", "CloudStack", "vendor", "Wants five minutes about cloud software", "low", "screened"),
        ("demo-c6", "+18885550997", "Unknown", "", "spam", "Press one", "low", "blocked"),
        ("demo-c7", "+18885550996", "Unknown", "", "spam", "Final notice", "low", "blocked"),
    ]
    for i, (cid, ph, name, co, tier, reason, pri, outcome) in enumerate(rows):
        started = (last_night + timedelta(minutes=45 * i)).isoformat(timespec="seconds")
        db.execute("INSERT INTO calls (call_id, caller_phone, caller_name, company, tier, reason, priority, outcome, summary, started_at)"
                   " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (cid, ph, name, co, tier, reason, pri, outcome, f"{name}: {reason}.", started))
    db.add_message(call_id="demo-c1", for_key="exec", from_name="Tom Becker", from_phone="+16155550302",
                   company="Becker & Stone LLP", reason="Lease amendment needs your signature by Friday",
                   details="DocuSign sent last night.", priority="high", created_at=(last_night + timedelta(hours=1)).isoformat())
    db.add_message(call_id="demo-c5", for_key="exec", from_name="Kevin Pratt", from_phone="+16155550500",
                   company="CloudStack", reason="Vendor pitch: cloud cost software", details="Sent details to vendor inbox.",
                   priority="low", created_at=(last_night + timedelta(hours=3)).isoformat())
    db.log_action("travis_voice", "booked", f"Alicia Moreno (Ridgeview Partners) intro for {d1.strftime('%A')} 11:00", "demo-c2")
    db.add_followup("Sign Becker & Stone lease amendment", "exec", today.isoformat(), "Tom Becker", "demo-c1")
    db.add_memory("Catherine Blake", "Prefers 'Cate'. Wants direct answers, no options.", "onboarding", "callers")
    db.add_memory("exec", "Car to the airport tomorrow at 5:45 AM.", "exec_sms")
    return {k: v.id for k, v in ev.items()} | {"today": today.isoformat(), "tomorrow": d1.isoformat()}
