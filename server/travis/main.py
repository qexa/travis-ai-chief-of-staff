"""Travis Core: the HTTP surface.

  POST /vapi/webhook         Vapi server URL (tool-calls, transfer, end-of-call, assistant-request)
  POST /tools/{name}         Generic tool endpoint (Retell, Votel.ai / GHL custom actions, n8n, testing)
  POST /sms/inbound          Twilio inbound SMS (exec command channel + replies from callers)
  POST /exec/command         Same as SMS channel, JSON in/out (dashboard, testing)
  POST /briefing/run         Build (and optionally send) the morning briefing
  GET  /admin/{calls|messages|followups|actions|outbox}
  GET  /health
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from html import escape
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from . import db
from .briefing import run_briefing, send_reminders
from .commands import handle_exec_message
from .profile import DAY_KEYS, get_profile, normalize_phone
from .security import verify_admin, verify_twilio, verify_vapi
from .settings import get_settings
from .summaries import process_end_of_call
from .tools import CallContext, run_tool, transfer_destination
from .calendar.availability import executive_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("travis")


# ── briefing scheduler (in-process; use cron + /briefing/run if you run >1 worker) ──
async def _briefing_loop() -> None:
    while True:
        try:
            p = get_profile()
            b = p.data.get("briefing", {})
            now = p.now()
            if b.get("enabled") and DAY_KEYS[now.weekday()] in b.get("days", DAY_KEYS[:5]) \
                    and now.strftime("%H:%M") == b.get("send_at", "06:45") \
                    and db.kv_get("briefing_sent_on") != now.date().isoformat():
                run_briefing(send=True)
                db.kv_set("briefing_sent_on", now.date().isoformat())
                log.info("Morning briefing sent")
            r = p.data.get("reminders", {})
            if r.get("enabled") and now.strftime("%H:%M") == r.get("send_at", "18:00") \
                    and db.kv_get("reminders_sent_on") != now.date().isoformat():
                db.kv_set("reminders_sent_on", now.date().isoformat())
                log.info("Sent %d attendee reminders", send_reminders())
        except Exception:
            log.exception("briefing loop error")
        await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.conn()
    task = None
    import os
    if os.environ.get("TRAVIS_SCHEDULER", "true").lower() == "true":
        task = asyncio.create_task(_briefing_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="Travis Core", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, Any]:
    s = get_settings()
    return {"ok": True, "exec": get_profile().exec["name"], "calendar": s.calendar_backend,
            "sms": s.sms_enabled, "email": s.email_enabled, "llm": s.llm_enabled}


# ── Vapi ────────────────────────────────────────────────────────────────────
def _ctx_from_vapi(message: dict[str, Any]) -> CallContext:
    call = message.get("call") or {}
    customer = call.get("customer") or message.get("customer") or {}
    return CallContext(call_id=call.get("id", ""), caller_phone=normalize_phone(customer.get("number", "")))


def _tool_args(tc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    fn = tc.get("function") or {}
    name = fn.get("name") or tc.get("name", "")
    args = fn.get("arguments", tc.get("arguments", tc.get("parameters", {})))
    if isinstance(args, str):
        try:
            args = json.loads(args or "{}")
        except json.JSONDecodeError:
            args = {}
    return name, args or {}


def assistant_variables() -> dict[str, str]:
    p = get_profile()
    now = p.now()
    status = executive_status(p)
    t = p.data.get("travis", {})
    greeting = (t.get("greeting_business_hours") if p.is_business_hours(now) else t.get("greeting_after_hours", "")) or ""
    return {
        "exec_name": p.exec["name"],
        "exec_first_name": p.exec["first_name"],
        "exec_ref": p.exec.get("caller_facing_name", p.exec["first_name"]),
        "exec_title": p.exec.get("title", ""),
        "company": p.exec.get("company", ""),
        "pronoun": p.exec.get("pronoun", "they"),
        "now": now.strftime("%A, %B %-d, %Y, %-I:%M %p"),
        "timezone": p.exec.get("timezone", ""),
        "part_of_day": p.part_of_day(now),
        "greeting": " ".join(greeting.replace("{part_of_day}", p.part_of_day(now))
                             .replace("{recording_notice}", t.get("recording_notice", "")).split()),
        "exec_status": status["public_status"],
        "recording_notice": t.get("recording_notice", ""),
        "team_directory": "; ".join(f"{m['name']} ({m['role']}): {', '.join(m.get('handles', []))}" for m in p.team),
    }


@app.post("/vapi/webhook", dependencies=[Depends(verify_vapi)])
async def vapi_webhook(request: Request) -> Response:
    body = await request.json()
    message = body.get("message", body)
    mtype = message.get("type", "")
    ctx = _ctx_from_vapi(message)

    if mtype == "assistant-request":
        s = get_settings()
        if not s.vapi_assistant_id:
            return JSONResponse({"error": "VAPI_ASSISTANT_ID not configured"})
        return JSONResponse({"assistantId": s.vapi_assistant_id,
                             "assistantOverrides": {"variableValues": assistant_variables()}})

    if mtype == "tool-calls":
        if ctx.call_id:
            db.start_call(ctx.call_id, ctx.caller_phone)
        results = []
        for tc in message.get("toolCallList") or message.get("toolCalls") or []:
            name, args = _tool_args(tc)
            out = run_tool(name, args, ctx)
            log.info("tool %s(%s) -> %s", name, args, out.get("action") or out.get("error") or "ok")
            results.append({"toolCallId": tc.get("id", ""), "name": name, "result": json.dumps(out, default=str)})
        return JSONResponse({"results": results})

    if mtype == "transfer-destination-request":
        dest = transfer_destination(ctx)
        if not dest:
            return JSONResponse({"error": "No transfer destination for this call. Take a message instead."})
        return JSONResponse({"destination": {"type": "number", "number": dest["number"],
                                             "message": f"Connecting you to {dest['name']} now."}})

    if mtype == "status-update" and message.get("status") == "in-progress" and ctx.call_id:
        db.start_call(ctx.call_id, ctx.caller_phone)
        return JSONResponse({})

    if mtype == "end-of-call-report":
        return JSONResponse(process_end_of_call(message))

    return JSONResponse({})


# ── Generic tools endpoint (Retell / Votel.ai / GHL / n8n / curl) ───────────
@app.post("/tools/{name}", dependencies=[Depends(verify_admin)])
async def generic_tool(name: str, request: Request) -> dict[str, Any]:
    body = await request.json()
    call = body.get("call") or {}
    args = body.get("args") or {k: v for k, v in body.items() if k not in ("call", "call_id", "caller_phone")}
    ctx = CallContext(call_id=call.get("call_id") or body.get("call_id", ""),
                      caller_phone=normalize_phone(call.get("from_number") or body.get("caller_phone", "")))
    if ctx.call_id:
        db.start_call(ctx.call_id, ctx.caller_phone)
    return run_tool(name, args, ctx)


# ── SMS ─────────────────────────────────────────────────────────────────────
def _twiml(text: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>',
                    media_type="application/xml")


@app.post("/sms/inbound")
async def sms_inbound(request: Request) -> Response:
    form = dict((await request.form()).items())
    params = {k: str(v) for k, v in form.items()}
    verify_twilio(request, params)
    sender, text = normalize_phone(params.get("From", "")), params.get("Body", "").strip()
    p = get_profile()
    if p.is_command_number(sender):
        return _twiml(handle_exec_message(text))
    # Anyone else (e.g. a caller replying to a confirmation) becomes a message for the exec.
    contact = db.find_contact_by_phone(sender) or {}
    db.add_message(for_key="exec", from_name=contact.get("name", "Text from " + sender), from_phone=sender,
                   company=contact.get("company", ""), reason="Text message", details=text[:1000], priority="normal")
    return _twiml(f"Thanks, this is TRAVIS in {p.exec['name']}'s office. I've passed your message along.")


@app.post("/exec/command", dependencies=[Depends(verify_admin)])
async def exec_command(request: Request) -> dict[str, str]:
    body = await request.json()
    return {"reply": handle_exec_message(body.get("text", ""))}


# ── Briefing + admin views ──────────────────────────────────────────────────
@app.post("/briefing/run", dependencies=[Depends(verify_admin)])
def briefing_run(send: bool = False) -> PlainTextResponse:
    return PlainTextResponse(run_briefing(send=send))


@app.get("/admin/assistant-variables", dependencies=[Depends(verify_admin)])
def admin_vars() -> dict[str, str]:
    return assistant_variables()


@app.post("/admin/reload", dependencies=[Depends(verify_admin)])
def admin_reload() -> dict[str, Any]:
    """Pick up edits to the executive profile and knowledge base without a restart."""
    from . import knowledge
    from .profile import reload_profile
    p = reload_profile()
    knowledge.reset_index()
    return {"reloaded": True, "exec": p.exec["name"], "vips": len(p.data.get("vips", []))}


ADMIN_TABLES = {"calls": "started_at", "messages": "created_at", "followups": "created_at",
                "actions": "created_at", "outbox": "created_at", "contacts": "created_at", "memories": "created_at"}


@app.get("/admin/{table}", dependencies=[Depends(verify_admin)])
def admin_table(table: str, limit: int = 50) -> list[dict[str, Any]]:
    if table not in ADMIN_TABLES:
        return []
    return db.query(f"SELECT * FROM {table} ORDER BY {ADMIN_TABLES[table]} DESC LIMIT ?", (min(limit, 500),))

