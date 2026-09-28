"""End-of-call processing: every call leaves a record, a summary, and owners for next steps."""
from __future__ import annotations

from typing import Any

from . import db, notify
from .profile import get_profile, normalize_phone
from .tools import CALL_STATE


def process_end_of_call(message: dict[str, Any]) -> dict[str, Any]:
    p = get_profile()
    call = message.get("call", {}) or {}
    call_id = call.get("id", "")
    phone = normalize_phone((call.get("customer") or {}).get("number", ""))
    analysis = message.get("analysis", {}) or {}
    artifact = message.get("artifact", {}) or {}
    structured = analysis.get("structuredData") or {}
    summary = (analysis.get("summary") or message.get("summary") or "").strip()
    transcript = artifact.get("transcript") or message.get("transcript") or ""
    recording = (artifact.get("recording") or {}).get("url") if isinstance(artifact.get("recording"), dict) else artifact.get("recordingUrl", "")

    state = CALL_STATE.pop(call_id, {})
    existing = db.one("SELECT * FROM calls WHERE call_id = ?", (call_id,)) or {}
    tier = existing.get("tier") or (state.get("caller").tier if state.get("caller") else "unknown")
    priority = structured.get("priority") or existing.get("priority") or "normal"
    outcome = existing.get("outcome") or structured.get("outcome") or ("blocked" if tier == "spam" else "answered")
    caller_name = existing.get("caller_name") or structured.get("caller_name") or "Unknown caller"

    db.update_call(call_id, caller_phone=phone, summary=summary, transcript=transcript, recording_url=recording or "",
                   ended_reason=message.get("endedReason", ""), ended_at=db.utcnow_iso(),
                   priority=priority, outcome=outcome, tier=tier, caller_name=caller_name)
    if tier == "spam":
        db.log_action("travis_voice", "blocked_spam", phone or "unknown number", call_id)

    for item in structured.get("action_items", []) or []:
        if isinstance(item, dict) and item.get("title"):
            db.add_followup(item["title"], item.get("owner", "exec"), item.get("due_date"), caller_name, call_id)

    skip = tier in p.data.get("call_summaries", {}).get("skip_for_tiers", ["spam"])
    sms_for = p.data.get("call_summaries", {}).get("sms_for_priority", ["critical", "high"])
    if not skip and priority in sms_for and summary:
        notify.send_sms(p.exec["mobile"], f"TRAVIS call summary ({priority}): {caller_name}. {summary[:600]}")
    return {"call_id": call_id, "tier": tier, "priority": priority, "outcome": outcome}
