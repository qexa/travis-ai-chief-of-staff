"""The voice tools. Each function receives the model's arguments plus call context
and returns a small JSON-able dict that TRAVIS reads back in the conversation.

Rule of thumb: tools return FACTS and a short `say` hint, never long prose.
Anything the model shouldn't read aloud (phone numbers, private notes) is
kept out of the result or marked internal.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable

from . import db, knowledge, notify
from .calendar import get_calendar
from .calendar.availability import executive_status, find_slots, is_slot_valid
from .profile import Profile, get_profile, normalize_phone
from .routing import Caller, assess_urgency, classify_caller, decide

log = logging.getLogger("travis.tools")


@dataclass
class CallContext:
    call_id: str = ""
    caller_phone: str = ""
    channel: str = "voice"          # voice | exec_sms
    extra: dict[str, Any] = field(default_factory=dict)


# Per-call scratchpad (tier, decision). Lives for the process; the calls table is the durable record.
CALL_STATE: dict[str, dict[str, Any]] = {}


def _state(ctx: CallContext) -> dict[str, Any]:
    return CALL_STATE.setdefault(ctx.call_id or "no-call", {})


def _caller(profile: Profile, ctx: CallContext, name: str = "", company: str = "", reason: str = "") -> Caller:
    st = _state(ctx)
    cached: Caller | None = st.get("caller")
    if cached and cached.tier not in ("unknown",) and not reason:
        return cached
    c = classify_caller(profile, ctx.caller_phone, name or (cached.name if cached else ""),
                        company or (cached.company if cached else ""), reason)
    st["caller"] = c
    return c


def _parse_dt(value: str, profile: Profile) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=profile.tz)
    return dt.astimezone(profile.tz)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _meeting_minutes(profile: Profile, meeting_type: str, duration: int | None, scope: str) -> tuple[str, int]:
    types = profile.calendar.get("meeting_types", {})
    if scope == "intro_only":
        meeting_type = "intro"
    mt = types.get(meeting_type) or types.get("standard") or {"minutes": 30}
    minutes = int(duration or mt["minutes"])
    if scope == "intro_only":
        minutes = min(minutes, types.get("intro", {}).get("minutes", 15))
    return meeting_type if meeting_type in types else "standard", max(10, min(minutes, 120))


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────
def lookup_caller(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx, args.get("name", ""), args.get("company", ""))
    db.update_call(ctx.call_id, caller_phone=ctx.caller_phone, caller_name=c.name, company=c.company, tier=c.tier)
    # Never hand remembered details to an unverified caller (someone claiming a VIP's name).
    facts = [m["fact"] for m in db.search_memories(c.name, visibility="callers")] if (c.name and c.verified) else []
    result = {
        "known": c.known,
        "tier": c.tier,
        "name": c.name or None,
        "company": c.company or None,
        "relationship": c.relationship or None,
        "greet_by_name": c.known and bool(c.name) and c.tier != "spam",
        "handling_notes": c.notes or None,
        "previous_calls": c.history.get("call_count", 0),
        "things_to_remember": facts[:3],
    }
    if c.tier == "unknown":
        result["next"] = "Ask for their name, company and the reason for the call, then call route_call."
    else:
        result["next"] = "Ask how you can help (if not already clear), then call route_call with the reason."
    return result


def get_executive_status(args: dict, ctx: CallContext) -> dict:
    s = executive_status(get_profile())
    # Only the caller-safe fields go back to the model.
    return {"public_status": s["public_status"], "state": s["state"], "free_at": s["free_at_spoken"]}


def route_call(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    reason = args.get("reason", "")
    c = _caller(p, ctx, args.get("caller_name", ""), args.get("company", ""), reason)
    urgency = assess_urgency(p, reason, args.get("urgency", "normal"))
    status = executive_status(p)
    d = decide(p, c, reason, urgency, status)
    st = _state(ctx)
    st.update({"decision": d, "reason": reason, "urgency": urgency})
    db.update_call(ctx.call_id, caller_phone=ctx.caller_phone, caller_name=c.name or args.get("caller_name", ""),
                   company=c.company or args.get("company", ""), tier=c.tier, reason=reason, priority=d.priority)

    if d.alert_exec and d.action in ("transfer_exec", "offer_callback", "take_message", "transfer_team"):
        who = c.name or args.get("caller_name") or "Unknown caller"
        co = f" ({c.company})" if c.company else ""
        notify.send_sms(p.exec["mobile"], f"TRAVIS · {d.priority.upper()}: {who}{co} is on the line now. Re: {reason or 'not stated'}. "
                                         f"Action: {d.action.replace('_', ' ')}.")
    out = {"action": d.action, "priority": d.priority, "say": d.say, "exec_status": status["public_status"]}
    if d.action in ("transfer_exec", "transfer_team"):
        out["transfer_to"] = d.transfer_name
        out["how"] = "Call the transfer_call tool now. Do not read out any phone number."
        out["if_no_answer"] = d.fallback
    if d.callback_time:
        out["callback_time"] = d.callback_time
    if d.booking_scope:
        out["booking_scope"] = d.booking_scope
    if d.route_to != "exec":
        member = p.team_member(d.route_to) or {}
        out["message_for"] = member.get("name", d.route_to)
    return out


def check_availability(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx)
    scope = _state(ctx).get("decision").booking_scope if _state(ctx).get("decision") else ""
    scope = scope or p.tiers.get(c.tier, {}).get("booking_scope", "standard")
    if ctx.channel == "exec_sms":
        scope = "extended"
    if ctx.channel != "exec_sms" and not p.tiers.get(c.tier, {}).get("can_book_directly", False):
        return {"slots": [], "say": "Booking isn't available for this call. Take a message instead."}
    mtype, minutes = _meeting_minutes(p, args.get("meeting_type", "standard"), args.get("duration_minutes"), scope)
    slots = find_slots(p, minutes, "extended" if scope == "extended" else "standard",
                       _parse_date(args.get("earliest_date")), _parse_date(args.get("latest_date")),
                       args.get("part_of_day", "any"), limit=3)
    if not slots:
        return {"slots": [], "say": "Nothing open in that window. Offer a different week or take a message and promise a callback with times."}
    return {"meeting_type": mtype, "duration_minutes": minutes,
            "slots": [s.as_dict(p.tz) for s in slots],
            "say": "Offer at most two of these naturally, e.g. 'I have Tuesday at 10 or Thursday at 2. Which works better?'"}


def book_meeting(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx)
    decision = _state(ctx).get("decision")
    scope = (decision.booking_scope if decision else "") or p.tiers.get(c.tier, {}).get("booking_scope", "standard")
    if ctx.channel == "exec_sms":
        scope = "extended"
    elif not p.tiers.get(c.tier, {}).get("can_book_directly", False):
        return {"booked": False, "say": "I can't book this one directly. Take a message."}
    try:
        start = _parse_dt(args["start"], p)
    except (KeyError, ValueError):
        return {"booked": False, "say": "I need the exact start time from check_availability."}
    mtype, minutes = _meeting_minutes(p, args.get("meeting_type", "standard"), args.get("duration_minutes"), scope)
    ok, why = is_slot_valid(p, start, minutes, "extended" if scope == "extended" else "standard")
    if not ok:
        return {"booked": False, "reason": why, "say": "That time just became unavailable. Call check_availability again and offer new times."}

    name = args.get("attendee_name") or c.name or "Guest"
    company = args.get("company") or c.company
    phone = normalize_phone(args.get("attendee_phone") or ctx.caller_phone)
    email = args.get("attendee_email", "")
    topic = args.get("topic", "")
    video = p.calendar.get("meeting_types", {}).get(mtype, {}).get("video", True)
    title = f"{name}{' (' + company + ')' if company else ''} / {p.exec['first_name']}: {topic or mtype.title()}"
    ev = get_calendar().create_event(
        title, start, start + timedelta(minutes=minutes),
        [{"name": name, "email": email, "phone": phone}],
        location=p.calendar.get("default_video_link", "") if video else "",
        notes=f"Booked by TRAVIS on a call. Tier: {c.tier}. Topic: {topic}. Call ID: {ctx.call_id}",
    )
    db.upsert_contact(name, phone, company, tier=c.tier if c.tier not in ("unknown",) else "new_opportunity", email=email)
    when = start.strftime("%A %B %-d at %-I:%M %p").replace(":00 ", " ")
    db.log_action("travis_voice" if ctx.channel == "voice" else "travis_sms", "booked", f"{title} on {when}", ctx.call_id)
    db.update_call(ctx.call_id, outcome="booked")
    _state(ctx)["booked_event"] = ev.id

    confirm = f"Confirmed: {p.exec['caller_facing_name']} on {when} ({minutes} min)."
    if phone and ctx.channel == "voice":
        notify.send_sms(phone, f"{confirm} {'Video link: ' + ev.location if ev.location else ''} "
                               f"Reply here or call back to change it. {p.data.get('travis', {}).get('company_line', '')}".strip())
    if c.tier in ("vip",):
        notify.send_sms(p.exec["mobile"], f"TRAVIS: booked {name} ({company}) {when}, {minutes} min. Topic: {topic or 'n/a'}.")
    return {"booked": True, "event_id": ev.id, "when": when, "duration_minutes": minutes,
            "confirmation_texted": bool(phone and ctx.channel == "voice"),
            "say": f"Confirm the time back to them: {when}. Mention a confirmation text is on its way"
                   + (" and ask for an email for the invite." if not email else ".")}


def find_my_meeting(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx)
    now = p.now()
    events = get_calendar().list_events(now, now + timedelta(days=30))
    name = args.get("name") or c.name
    mine = [e for e in events if e.attendee_matches(name=name if not ctx.caller_phone else "", phone=ctx.caller_phone,
                                                    email=args.get("email", ""))]
    if not mine and name and c.verified:
        mine = [e for e in events if e.attendee_matches(name=name)]
    if not mine:
        return {"found": False, "say": "Say you don't see a meeting under their name or number and ask for the email the invite went to, or take a message."}
    return {"found": True, "meetings": [{"event_id": e.id,
                                          "when": e.start.astimezone(p.tz).strftime("%A %B %-d at %-I:%M %p").replace(":00 ", " "),
                                          "duration_minutes": int((e.end - e.start).total_seconds() // 60)} for e in mine[:3]]}


def reschedule_meeting(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    if ctx.channel == "voice" and not p.calendar.get("caller_can_reschedule", True):
        return {"moved": False, "say": "Take a message; the office will confirm a new time."}
    cal = get_calendar()
    ev = cal.get_event(args.get("event_id", ""))
    if not ev:
        return {"moved": False, "say": "I couldn't find that meeting. Use find_my_meeting first."}
    if ctx.channel == "voice" and not ev.attendee_matches(phone=ctx.caller_phone, name=_caller(p, ctx).name if _caller(p, ctx).verified else ""):
        return {"moved": False, "say": "For privacy I can only move a meeting for someone on the invite. Take a message instead."}
    try:
        new_start = _parse_dt(args["new_start"], p)
    except (KeyError, ValueError):
        return {"moved": False, "say": "Call check_availability first and use one of its exact start times."}
    minutes = int((ev.end - ev.start).total_seconds() // 60)
    scope = "extended" if ctx.channel == "exec_sms" else "standard"
    ok, why = is_slot_valid(p, new_start, minutes, scope, ignore_event_id=ev.id)
    if not ok:
        return {"moved": False, "reason": why, "say": "That time isn't open. Offer the times from check_availability."}
    old = ev.start.astimezone(p.tz).strftime("%a %-I:%M %p")
    moved = cal.move_event(ev.id, new_start, new_start + timedelta(minutes=minutes))
    when = moved.start.astimezone(p.tz).strftime("%A %B %-d at %-I:%M %p").replace(":00 ", " ")
    db.log_action("travis_voice" if ctx.channel == "voice" else "travis_sms", "rescheduled",
                  f"{ev.title}: {old} → {when}", ctx.call_id)
    db.update_call(ctx.call_id, outcome="rescheduled")
    if ctx.channel == "voice" and ctx.caller_phone:
        notify.send_sms(ctx.caller_phone, f"Updated: your meeting with {p.exec['caller_facing_name']} is now {when}. The new invite is on its way.")
    return {"moved": True, "when": when, "say": f"Confirm: it's moved to {when} and the updated invite is on its way."}


def take_message(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx)
    st = _state(ctx)
    decision = st.get("decision")
    priority = args.get("priority") or (decision.priority if decision else "normal")
    priority = assess_urgency(p, f"{args.get('reason', '')} {args.get('details', '')}", priority)
    for_key = args.get("for_whom") or (decision.route_to if decision else "exec")
    if for_key not in ("exec",) and not p.team_member(for_key):
        match = next((t for t in p.team if t["name"].lower().startswith(str(for_key).lower())), None)
        for_key = match["key"] if match else "exec"
    name = args.get("caller_name") or c.name or "Unknown caller"
    phone = normalize_phone(args.get("callback_number") or ctx.caller_phone)
    company = args.get("company") or c.company
    mid = db.add_message(call_id=ctx.call_id, for_key=for_key, from_name=name, from_phone=phone, company=company,
                         reason=args.get("reason", ""), details=args.get("details", ""), priority=priority,
                         callback_window=args.get("best_time_to_call", ""))
    if c.tier not in ("spam",):
        db.upsert_contact(name, phone, company, tier=c.tier if c.tier != "unknown" else "new_opportunity")
    db.update_call(ctx.call_id, outcome="message", priority=priority)

    # Deliver high-priority messages immediately; the rest roll into the briefing.
    recipient = p.exec if for_key == "exec" else p.team_member(for_key)
    line = (f"TRAVIS · {priority.upper()} message from {name}{' (' + company + ')' if company else ''}, "
            f"{phone or 'no number'}: {args.get('reason', '')}. {args.get('details', '')} "
            f"Best time: {args.get('best_time_to_call') or 'any'}.")
    if priority in p.data.get("call_summaries", {}).get("sms_for_priority", ["critical", "high"]) or for_key != "exec":
        notify.send_sms(recipient["mobile" if for_key == "exec" else "phone"], line)
        db.execute("UPDATE messages SET status = 'delivered' WHERE id = ?", (mid,))
    if for_key != "exec":
        db.add_followup(f"Return call: {name} re {args.get('reason', '')}", owner_key=for_key,
                        due_at=(p.now() + timedelta(days=1)).isoformat(), related_contact=name, related_call_id=ctx.call_id)
    who = p.pronoun_forms()["obj"] if for_key == "exec" else recipient["name"]
    return {"saved": True, "message_id": mid, "priority": priority, "delivered_to": "executive" if for_key == "exec" else recipient["name"],
            "say": f"Read back the callback number, confirm you'll get this to {who}"
                   + (" right away" if priority in ("high", "critical") else "") + "."}


def search_knowledge(args: dict, ctx: CallContext) -> dict:
    hits = knowledge.search(args.get("query", ""), include_private=ctx.channel == "exec_sms")
    if not hits:
        return {"found": False, "say": "Say you don't have that detail handy and offer to have the right person follow up. Do not guess."}
    return {"found": True, "passages": hits, "say": "Answer briefly from these passages only. If they don't cover it, offer a follow-up."}


def create_followup(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    owner = args.get("owner", "exec")
    if owner != "exec" and not p.team_member(owner):
        match = next((t for t in p.team if t["name"].lower().startswith(owner.lower()) or owner.lower() in t["role"].lower()), None)
        owner = match["key"] if match else "exec"
    due = args.get("due_date") or (p.now() + timedelta(days=1)).date().isoformat()
    fid = db.add_followup(args.get("title", "Follow up"), owner, due, args.get("related_contact", ""), ctx.call_id)
    if owner != "exec":
        m = p.team_member(owner)
        notify.send_sms(m["phone"], f"TRAVIS assigned you a follow-up (due {due}): {args.get('title')}")
    return {"created": True, "followup_id": fid, "owner": owner, "due": due}


def note_about_caller(args: dict, ctx: CallContext) -> dict:
    p = get_profile()
    c = _caller(p, ctx)
    subject = args.get("subject") or c.name or ctx.caller_phone or "unknown"
    fact = (args.get("fact") or "").strip()
    if not fact:
        return {"saved": False}
    db.add_memory(subject, fact, source="call", visibility=args.get("visibility", "private"))
    return {"saved": True}


def text_caller_info(args: dict, ctx: CallContext) -> dict:
    """Text the caller one pre-approved snippet (never free text written by the model)."""
    p = get_profile()
    texts = p.data.get("caller_texts", {})
    key = args.get("info", "")
    if key not in texts:
        return {"sent": False, "say": f"You can only text: {', '.join(texts) or 'nothing configured'}."}
    to = normalize_phone(args.get("phone") or ctx.caller_phone)
    if not to:
        return {"sent": False, "say": "Ask for a mobile number to text it to."}
    notify.send_sms(to, texts[key])
    db.log_action("travis_voice", "texted_info", f"{key} to {to}", ctx.call_id)
    return {"sent": True, "say": "Tell them the text is on its way."}


def transfer_destination(ctx: CallContext) -> dict | None:
    """Used by the voice-platform transfer hook: returns where to send the live call."""
    d = _state(ctx).get("decision")
    if not d or not d.transfer_number:
        return None
    db.log_action("travis_voice", "transferred", f"to {d.transfer_name}", ctx.call_id)
    db.update_call(ctx.call_id, outcome="transferred")
    return {"number": d.transfer_number, "name": d.transfer_name}


TOOLS: dict[str, Callable[[dict, CallContext], dict]] = {
    "lookup_caller": lookup_caller,
    "get_executive_status": get_executive_status,
    "route_call": route_call,
    "check_availability": check_availability,
    "book_meeting": book_meeting,
    "find_my_meeting": find_my_meeting,
    "reschedule_meeting": reschedule_meeting,
    "take_message": take_message,
    "search_knowledge": search_knowledge,
    "create_followup": create_followup,
    "note_about_caller": note_about_caller,
    "text_caller_info": text_caller_info,
}


def run_tool(name: str, args: dict, ctx: CallContext) -> dict:
    fn = TOOLS.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(args or {}, ctx)
    except Exception as exc:  # a tool error must never crash a live call
        log.exception("tool %s failed", name)
        return {"error": "tool_failed", "detail": str(exc)[:200],
                "say": "Apologize briefly, take a detailed message instead, and promise a prompt follow-up."}
