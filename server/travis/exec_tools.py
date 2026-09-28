"""Tools only the executive can use (via the SMS command channel). Never exposed to callers."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from . import db
from .calendar import get_calendar
from .calendar.availability import find_slots, is_slot_valid
from .profile import get_profile
from .tools import CallContext

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_day(text: str, today: date) -> date | None:
    t = text.lower()
    if "today" in t:
        return today
    if "tomorrow" in t:
        return today + timedelta(days=1)
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b({name}|{name[:3]})\b", t):
            delta = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=delta)
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    return date.fromisoformat(m.group(1)) if m else None


def parse_time(text: str) -> time | None:
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\b", text.lower())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "")
    if h > 23 or mi > 59:
        return None
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    elif not ap and 1 <= h <= 6:   # "move my 2 to friday" → 2 PM
        h += 12
    return time(h, mi)


def _fmt(dt: datetime) -> str:
    return dt.astimezone(get_profile().tz).strftime("%a %b %-d, %-I:%M %p").replace(":00 ", " ")


# ── tools ───────────────────────────────────────────────────────────────────
def get_schedule(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    d = date.fromisoformat(args["date"]) if args.get("date") else p.now().date()
    start = datetime.combine(d, time(0), p.tz)
    evs = get_calendar().list_events(start, start + timedelta(days=1))
    return {"date": d.isoformat(), "events": [
        {"event_id": e.id, "start": _fmt(e.start), "end": e.end.astimezone(p.tz).strftime("%-I:%M %p"),
         "title": e.title, "kind": e.kind} for e in evs]}


def who_called(args: dict, ctx: CallContext) -> dict:
    days = int(args.get("days", 3))
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    q = (args.get("query") or "").lower()
    rows = db.query("SELECT caller_name, company, caller_phone, reason, priority, outcome, summary, started_at "
                    "FROM calls WHERE started_at >= ? AND (tier IS NULL OR tier != 'spam') ORDER BY started_at DESC", (since,))
    if q:
        rows = [r for r in rows if q in " ".join(str(v or "") for v in r.values()).lower()]
    msgs = db.query("SELECT id, from_name, company, from_phone, reason, details, priority, status FROM messages "
                    "WHERE created_at >= ? ORDER BY created_at DESC", (since,))
    if q:
        msgs = [m for m in msgs if q in " ".join(str(v or "") for v in m.values()).lower()]
    return {"calls": rows[:10], "messages": msgs[:10]}


def remember(args: dict, ctx: CallContext) -> dict:
    fact = (args.get("fact") or "").strip()
    if not fact:
        return {"saved": False}
    db.add_memory(args.get("subject") or "exec", fact, source="exec_sms",
                  visibility=args.get("visibility", "private"))
    return {"saved": True, "fact": fact}


def recall(args: dict, ctx: CallContext) -> dict:
    return {"memories": [{"subject": m["subject"], "fact": m["fact"], "saved": m["created_at"][:10]}
                         for m in db.search_memories(args.get("query", ""))]}


def move_meeting(args: dict, ctx: CallContext) -> dict:
    """Exec version of reschedule: may pick any valid slot, including extended hours."""
    p = get_profile()
    cal = get_calendar()
    ev = cal.get_event(args.get("event_id", ""))
    if not ev:
        return {"moved": False, "error": "event not found; call get_schedule first"}
    minutes = int((ev.end - ev.start).total_seconds() // 60)
    if args.get("new_start"):
        new_start = datetime.fromisoformat(args["new_start"])
        new_start = new_start if new_start.tzinfo else new_start.replace(tzinfo=p.tz)
        ok, why = is_slot_valid(p, new_start, minutes, "extended", ignore_event_id=ev.id)
        if not ok and not args.get("force"):
            return {"moved": False, "reason": why, "hint": "Ask the exec to confirm, then call again with force=true."}
    else:
        d = date.fromisoformat(args["new_date"])
        # Prefer normal meeting hours; fall back to the extended window only if the day is full.
        slots = (find_slots(p, minutes, "standard", d, d, limit=1, ignore_event_id=ev.id)
                 or find_slots(p, minutes, "extended", d, d, limit=1, ignore_event_id=ev.id))
        if not slots:
            return {"moved": False, "reason": "no open slot that day"}
        new_start = slots[0].start
    old = _fmt(ev.start)
    moved = cal.move_event(ev.id, new_start, new_start + timedelta(minutes=minutes))
    db.log_action("travis_sms", "rescheduled", f"{ev.title}: {old} → {_fmt(moved.start)}")
    return {"moved": True, "title": ev.title, "from": old, "to": _fmt(moved.start), "attendees_notified": True}


def block_time(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    start = datetime.fromisoformat(args["start"])
    start = start if start.tzinfo else start.replace(tzinfo=p.tz)
    end = datetime.fromisoformat(args["end"])
    end = end if end.tzinfo else end.replace(tzinfo=p.tz)
    ev = get_calendar().create_event(args.get("label", "Hold (TRAVIS)"), start, end, [], kind="focus")
    db.log_action("travis_sms", "blocked_time", f"{ev.title} {_fmt(start)}–{end.astimezone(p.tz).strftime('%-I:%M %p')}")
    return {"blocked": True, "event_id": ev.id, "when": _fmt(start)}


def cancel_meeting(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    if str(args.get("pin", "")) != str(p.exec.get("command_pin", "")):
        return {"cancelled": False, "error": "PIN required. Ask the exec to reply with their PIN."}
    ev = get_calendar().get_event(args.get("event_id", ""))
    if not ev:
        return {"cancelled": False, "error": "not found"}
    get_calendar().delete_event(ev.id)
    db.log_action("travis_sms", "cancelled", f"{ev.title} ({_fmt(ev.start)})")
    return {"cancelled": True, "title": ev.title}


def mark_handled(args: dict, ctx: CallContext) -> dict:
    if args.get("message_id"):
        db.execute("UPDATE messages SET status = 'handled' WHERE id = ?", (args["message_id"],))
        return {"handled": 1}
    name = args.get("from_name", "")
    rows = db.query("SELECT id FROM messages WHERE status != 'handled' AND lower(from_name) LIKE ?", (f"%{name.lower()}%",))
    for r in rows:
        db.execute("UPDATE messages SET status = 'handled' WHERE id = ?", (r["id"],))
    return {"handled": len(rows)}


def complete_followup(args: dict, ctx: CallContext) -> dict:
    q = (args.get("query") or "").lower()
    rows = db.query("SELECT id, title FROM followups WHERE status = 'open'")
    hit = [r for r in rows if q and q in r["title"].lower()]
    for r in hit:
        db.execute("UPDATE followups SET status = 'done' WHERE id = ?", (r["id"],))
    return {"completed": [r["title"] for r in hit]}


EXEC_TOOLS = {
    "get_schedule": get_schedule,
    "who_called": who_called,
    "remember": remember,
    "recall": recall,
    "move_meeting": move_meeting,
    "block_time": block_time,
    "cancel_meeting": cancel_meeting,
    "mark_handled": mark_handled,
    "complete_followup": complete_followup,
}


def exec_tool_schemas() -> list[dict[str, Any]]:
    """Anthropic-format tool definitions for the command channel."""
    s = lambda props, req=(): {"type": "object", "properties": props, "required": list(req)}  # noqa: E731
    string = {"type": "string"}
    return [
        {"name": "get_schedule", "description": "List the executive's calendar for a date (YYYY-MM-DD, default today).",
         "input_schema": s({"date": string})},
        {"name": "who_called", "description": "Recent calls and messages, optionally filtered by a keyword (name, company, topic).",
         "input_schema": s({"query": string, "days": {"type": "integer"}})},
        {"name": "remember", "description": "Save a fact the executive wants TRAVIS to remember. visibility 'callers' means it may be used on calls.",
         "input_schema": s({"fact": string, "subject": string, "visibility": {"type": "string", "enum": ["private", "callers"]}}, ["fact"])},
        {"name": "recall", "description": "Search saved memories.", "input_schema": s({"query": string}, ["query"])},
        {"name": "move_meeting", "description": "Move a meeting. Give new_start (ISO datetime) or new_date (YYYY-MM-DD, first open slot). force=true only after the exec confirms an override.",
         "input_schema": s({"event_id": string, "new_start": string, "new_date": string, "force": {"type": "boolean"}}, ["event_id"])},
        {"name": "block_time", "description": "Block time on the calendar (ISO datetimes).",
         "input_schema": s({"start": string, "end": string, "label": string}, ["start", "end"])},
        {"name": "cancel_meeting", "description": "Cancel a meeting. Requires the executive's PIN in this conversation.",
         "input_schema": s({"event_id": string, "pin": string}, ["event_id", "pin"])},
        {"name": "mark_handled", "description": "Mark messages as handled, by message_id or caller name.",
         "input_schema": s({"message_id": {"type": "integer"}, "from_name": string})},
        {"name": "complete_followup", "description": "Mark follow-ups done by keyword.", "input_schema": s({"query": string}, ["query"])},
        {"name": "check_availability", "description": "Find open slots. meeting_type intro|standard|investor.",
         "input_schema": s({"meeting_type": string, "duration_minutes": {"type": "integer"}, "earliest_date": string,
                            "latest_date": string, "part_of_day": {"type": "string", "enum": ["any", "morning", "afternoon", "evening"]}})},
        {"name": "book_meeting", "description": "Book a meeting at a start time returned by check_availability.",
         "input_schema": s({"start": string, "meeting_type": string, "duration_minutes": {"type": "integer"}, "attendee_name": string,
                            "attendee_email": string, "attendee_phone": string, "company": string, "topic": string}, ["start", "attendee_name"])},
        {"name": "create_followup", "description": "Create a follow-up task. owner is 'exec' or a team member key/name.",
         "input_schema": s({"title": string, "owner": string, "due_date": string, "related_contact": string}, ["title"])},
        {"name": "search_knowledge", "description": "Search the company knowledge base (includes internal notes on this channel).",
         "input_schema": s({"query": string}, ["query"])},
    ]
