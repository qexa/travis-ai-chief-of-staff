"""Executive command channel: the exec texts TRAVIS, TRAVIS acts.

Two engines:
  1. LLM agent (when ANTHROPIC_API_KEY is set): a tool-use loop over the exec
     tools, with the exec-channel prompt in prompts/exec-command-channel.md.
  2. Rule-based fallback (demo mode / LLM outage): handles the ten most common
     commands with regexes so the channel never goes dark.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, time, timedelta
from typing import Any

import httpx

from . import tools as voice_tools
from .briefing import run_briefing
from .exec_tools import EXEC_TOOLS, exec_tool_schemas, parse_day, parse_time
from .calendar import get_calendar
from .profile import get_profile
from .settings import REPO_ROOT, get_settings
from .tools import CallContext

log = logging.getLogger("travis.commands")
HISTORY: list[dict[str, Any]] = []   # short rolling context for the exec thread
MAX_HISTORY = 12


def _all_tools() -> dict:
    merged = dict(EXEC_TOOLS)
    for name in ("check_availability", "book_meeting", "create_followup", "search_knowledge"):
        merged[name] = voice_tools.TOOLS[name]
    return merged


def _system_prompt() -> str:
    p = get_profile()
    base = (REPO_ROOT / "prompts" / "exec-command-channel.md").read_text()
    now = p.now()
    return (base.replace("{{exec_name}}", p.exec["name"]).replace("{{honorific}}", p.exec.get("honorific", ""))
            .replace("{{now}}", now.strftime("%A, %B %-d, %Y %-I:%M %p")).replace("{{timezone}}", p.exec["timezone"]))


# ── LLM engine ──────────────────────────────────────────────────────────────
def _llm_turn(text: str) -> str:
    s = get_settings()
    ctx = CallContext(call_id="exec-sms", channel="exec_sms", caller_phone=get_profile().exec["mobile"])
    handlers = _all_tools()
    # HISTORY keeps only plain-text turns (user text / final replies), so it can be trimmed safely.
    messages = HISTORY[-MAX_HISTORY:] + [{"role": "user", "content": text}]
    while messages and messages[0]["role"] != "user":
        messages = messages[1:]
    for _ in range(8):
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=45, headers={
            "x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": s.llm_model, "max_tokens": 800, "system": _system_prompt(),
                  "tools": exec_tool_schemas(), "messages": messages})
        r.raise_for_status()
        body = r.json()
        messages.append({"role": "assistant", "content": body["content"]})
        if body.get("stop_reason") != "tool_use":
            reply = "".join(b.get("text", "") for b in body["content"] if b["type"] == "text").strip() or "Done."
            HISTORY.extend([{"role": "user", "content": text}, {"role": "assistant", "content": reply}])
            del HISTORY[:-MAX_HISTORY]
            return reply
        results = []
        for block in body["content"]:
            if block["type"] == "tool_use":
                fn = handlers.get(block["name"])
                out = fn(block["input"], ctx) if fn else {"error": "unknown tool"}
                results.append({"type": "tool_result", "tool_use_id": block["id"], "content": json.dumps(out, default=str)})
        messages.append({"role": "user", "content": results})
    return "I ran out of steps on that one. Can you break it into smaller asks?"


# ── Rule-based engine ───────────────────────────────────────────────────────
HELP = ("I can: brief · schedule [today|tomorrow|fri] · who called [about X] · move my 2pm to Friday [at 10] · "
        "block tomorrow 1-3 · remember <fact> · what do you know about <X> · done <name>")


def _rules(text: str) -> str:
    p = get_profile()
    ctx = CallContext(call_id="exec-sms", channel="exec_sms")
    t = text.strip()
    low = t.lower()
    today = p.now().date()

    if low in ("help", "?", "commands"):
        return HELP
    if re.match(r"^(brief|briefing|status|morning|update)\b", low):
        return run_briefing(send=False)
    m = re.match(r"^remember( that)?\s+(.+)$", t, re.I)
    if m:
        EXEC_TOOLS["remember"]({"fact": m.group(2)}, ctx)
        return f"Noted, {p.exec.get('honorific', '')}. I'll remember that.".replace(" .", ".")
    m = re.match(r"^(what do you know about|recall|what did i say about)\s+(.+?)\??$", low)
    if m:
        mem = EXEC_TOOLS["recall"]({"query": m.group(2)}, ctx)["memories"]
        return "\n".join(f"• {x['fact']} ({x['saved']})" for x in mem) or "Nothing saved on that yet."
    m = re.match(r"^who (called|rang)(?: about| re| regarding)?\s*(.*?)\??$", low)
    if m:
        res = EXEC_TOOLS["who_called"]({"query": m.group(2)}, ctx)
        rows = res["messages"] or res["calls"]
        if not rows:
            return "No calls matching that in the last 3 days."
        out = []
        for r in rows[:6]:
            name = r.get("from_name") or r.get("caller_name") or "Unknown"
            co = r.get("company")
            out.append(f"• {name}{', ' + co if co else ''}: {r.get('reason') or r.get('summary') or ''} [{r.get('priority', '')}]")
        return "\n".join(out)
    m = re.match(r"^(done|handled|called back)\s+(.+)$", low)
    if m:
        n = EXEC_TOOLS["mark_handled"]({"from_name": m.group(2)}, ctx)["handled"]
        return f"Marked {n} message{'s' if n != 1 else ''} handled."
    if re.match(r"^(schedule|calendar|agenda|what'?s on)", low):
        d = parse_day(low, today) or today
        ev = EXEC_TOOLS["get_schedule"]({"date": d.isoformat()}, ctx)["events"]
        if not ev:
            return f"{d.strftime('%A')} is clear."
        return f"{d.strftime('%A %b %-d')}:\n" + "\n".join(f"• {e['start'].split(', ')[-1]} {e['title']}" for e in ev)
    m = re.match(r"^(move|push|reschedule|shift)\s+(?:my\s+)?(.+?)\s+to\s+(.+)$", low)
    if m:
        src_day = parse_day(m.group(2), today) or today
        src_t = parse_time(m.group(2))
        start = datetime.combine(src_day, time(0), p.tz)
        evs = get_calendar().list_events(start, start + timedelta(days=1))
        target = next((e for e in evs if src_t and e.start.astimezone(p.tz).time() == src_t), None)
        if not target:
            target = next((e for e in evs if any(w in e.title.lower() for w in m.group(2).split() if len(w) > 3)), None)
        if not target:
            return "I couldn't find that meeting. Text \"schedule\" to see today's list."
        new_day = parse_day(m.group(3), today)
        new_t = parse_time(m.group(3))
        args: dict[str, Any] = {"event_id": target.id}
        if new_t:
            args["new_start"] = datetime.combine(new_day or src_day, new_t, p.tz).isoformat()
        elif new_day:
            args["new_date"] = new_day.isoformat()
        else:
            return "To when? e.g. \"to Friday\" or \"to Friday at 10\"."
        res = EXEC_TOOLS["move_meeting"](args, ctx)
        if res.get("moved"):
            return f"Done. {res['title']} moved from {res['from']} to {res['to']}. Attendees get the updated invite."
        return f"Can't move it there ({res.get('reason', res.get('error'))}). Want the next open time instead?"
    m = re.match(r"^(block|hold)\s+(.+)$", low)
    if m:
        d = parse_day(m.group(2), today) or today
        times = re.findall(r"\d{1,2}(?::\d{2})?\s*(?:am|pm)?", m.group(2))
        if len(times) >= 2:
            t0, t1 = parse_time(times[0]), parse_time(times[1])
            if t0 and t1:
                res = EXEC_TOOLS["block_time"]({"start": datetime.combine(d, t0, p.tz).isoformat(),
                                                "end": datetime.combine(d, t1, p.tz).isoformat()}, ctx)
                return f"Blocked {res['when']}."
        return "Give me a range, e.g. \"block Thursday 1-3pm\"."
    return f"Got it. I didn't catch an action there. {HELP}"


def handle_exec_message(text: str) -> str:
    if get_settings().llm_enabled:
        try:
            return _llm_turn(text)
        except Exception:
            log.exception("LLM command engine failed; falling back to rules")
    return _rules(text)
