"""The Morning Protocol: one message, before the exec's day starts, with the full picture.

    Good morning, sir. Five meetings today. I've moved your 10:00 to 2:30 and
    confirmed both attendees. Two items need your reply. Four spam calls blocked.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from . import db, notify
from .calendar import get_calendar
from .profile import Profile, get_profile, parse_hhmm

PRI = {"critical": 0, "high": 1, "normal": 2, "low": 3}
NUM = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"]


def _n(k: int) -> str:
    return NUM[k] if k < len(NUM) else str(k)


def _fmt_t(dt: datetime, tz) -> str:
    return dt.astimezone(tz).strftime("%-I:%M %p").replace(":00 ", " ")


def gather(profile: Profile, now: datetime | None = None) -> dict[str, Any]:
    tz = profile.tz
    now = (now or profile.now()).astimezone(tz)
    last = db.kv_get("last_briefing_at")
    if last:
        since = datetime.fromisoformat(last)
    else:
        start_t = parse_hhmm(profile.data.get("briefing", {}).get("overnight_window_start", "18:00"))
        since = datetime.combine(now.date() - timedelta(days=1), start_t, tz)
    since_utc = since.astimezone(timezone.utc).isoformat(timespec="seconds")

    day0 = datetime.combine(now.date(), time(0), tz)
    events = [e for e in get_calendar().list_events(day0, day0 + timedelta(days=1)) if e.end > now or e.start >= day0]
    calls = db.query("SELECT * FROM calls WHERE started_at >= ? ORDER BY started_at", (since_utc,))
    spam = [c for c in calls if c.get("tier") == "spam"]
    real_calls = [c for c in calls if c.get("tier") != "spam"]
    needs_reply = db.query("SELECT * FROM messages WHERE for_key = 'exec' AND status != 'handled' ORDER BY created_at DESC")
    needs_reply.sort(key=lambda m: PRI.get(m["priority"], 2))
    actions = db.query("SELECT * FROM actions WHERE created_at >= ? AND action IN ('booked','rescheduled','cancelled','blocked_time') "
                       "ORDER BY created_at", (since_utc,))
    followups = db.query("SELECT * FROM followups WHERE status = 'open' AND owner_key = 'exec' AND (due_at IS NULL OR due_at <= ?) "
                         "ORDER BY due_at", ((now + timedelta(days=1)).date().isoformat(),))
    return {"now": now, "since": since, "events": events, "calls": real_calls, "spam": spam,
            "needs_reply": needs_reply, "actions": actions, "followups": followups}


def render_text(profile: Profile, data: dict[str, Any]) -> str:
    tz = profile.tz
    ex = profile.exec
    meetings = [e for e in data["events"] if e.kind == "meeting"]
    travel = [e for e in data["events"] if e.kind == "travel"]
    lines = [f"Good morning, {ex.get('honorific', ex.get('first_name'))}."]

    head = f"{_n(len(meetings))} meeting{'s' if len(meetings) != 1 else ''} today"
    if meetings:
        head += f", first at {_fmt_t(meetings[0].start, tz)}"
    lines[0] += f" {head}."
    for a in data["actions"][:3]:
        verb = {"booked": "I booked", "rescheduled": "I moved", "cancelled": "I cancelled", "blocked_time": "I blocked"}[a["action"]]
        lines.append(f"{verb} {a['detail']}.")
    for t in travel[:2]:
        lines.append(f"Travel: {t.title} at {_fmt_t(t.start, tz)}.")

    lines.append("")
    lines.append(f"▸ {len(data['calls'])} calls handled overnight · {len(data['needs_reply'])} need your reply · "
                 f"{len(data['spam'])} spam blocked")

    if meetings:
        lines.append("")
        lines.append("TODAY")
        for e in meetings:
            who = ", ".join(a.get("name", "") for a in e.attendees if a.get("name"))
            lines.append(f"  {_fmt_t(e.start, tz)}  {e.title}" + (f" (with {who})" if who and who not in e.title else ""))

    if data["needs_reply"]:
        lines.append("")
        lines.append("NEEDS YOU")
        for m in data["needs_reply"][:5]:
            flag = "‼ " if m["priority"] in ("critical", "high") else ""
            co = f", {m['company']}" if m.get("company") else ""
            lines.append(f"  {flag}{m['from_name']}{co}: {m['reason'] or 'call back'}"
                         + (f" ({m['from_phone']})" if m.get("from_phone") else ""))

    if data["followups"]:
        lines.append("")
        lines.append("FOLLOW-UPS DUE")
        for f in data["followups"][:5]:
            lines.append(f"  • {f['title']}")

    lines.append("")
    lines.append("Reply with anything. \"Move my 2pm to Friday\", \"Who called about the term sheet?\"")
    return "\n".join(lines)


def send_reminders(now: datetime | None = None) -> int:
    """Text external attendees the evening before. Returns the number sent."""
    profile = get_profile()
    cfg = profile.data.get("reminders", {})
    if not cfg.get("enabled"):
        return 0
    tz = profile.tz
    now = (now or profile.now()).astimezone(tz)
    day0 = datetime.combine(now.date() + timedelta(days=1), time(0), tz)
    sent = 0
    for e in get_calendar().list_events(day0, day0 + timedelta(days=1)):
        if e.kind != "meeting":
            continue
        for a in e.attendees:
            if a.get("phone"):
                when = e.start.astimezone(tz).strftime("%-I:%M %p").replace(":00 ", " ")
                notify.send_sms(a["phone"], cfg.get("text", "Reminder: meeting tomorrow at {when}.")
                                .replace("{exec_ref}", profile.exec.get("caller_facing_name", profile.exec["name"]))
                                .replace("{when}", when))
                sent += 1
    return sent


def run_briefing(send: bool = True, now: datetime | None = None) -> str:
    profile = get_profile()
    data = gather(profile, now)
    text = render_text(profile, data)
    if send:
        channels = profile.data.get("briefing", {}).get("channels", ["sms"])
        if "sms" in channels:
            notify.send_sms(profile.exec["mobile"], text)
        if "email" in channels and profile.exec.get("email"):
            notify.send_email(profile.exec["email"], f"TRAVIS Systems Briefing · {data['now'].strftime('%A, %B %-d')}", text)
        db.kv_set("last_briefing_at", data["now"].isoformat())
        db.execute("UPDATE messages SET status = 'delivered' WHERE status = 'new'")
    return text
