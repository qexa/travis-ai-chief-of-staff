#!/usr/bin/env python3
"""Generate voice/tools/*.json and voice/vapi-assistant.json from ONE source of truth.

    python scripts/build_voice_config.py

Edit TOOLS below (not the JSON files) when you change a tool, then re-run.
The generated JSON is Vapi's format; docs/13-platform-notes.md maps it to
Retell, Votel.ai, Bland and ElevenLabs Agents.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = {"type": "string"}


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


URGENCY = {"type": "string", "enum": ["low", "normal", "high", "critical"],
           "description": "Your judgment. critical = safety, legal, or money at immediate risk. high = time-sensitive today."}

TOOLS = [
    ("lookup_caller", "Identify the caller from caller ID and return their tier, name and handling notes. Call this FIRST on every call.",
     obj({"name": {**S, "description": "Name the caller gave, if any"}, "company": S}), "One moment."),
    ("route_call", "Decide how to handle this call once you know who is calling and why. Returns an action to follow.",
     obj({"caller_name": S, "company": S, "reason": {**S, "description": "One sentence: why they are calling"},
          "urgency": URGENCY}, ["reason", "urgency"]), None),
    ("get_executive_status", "Caller-safe description of whether the executive is available right now, and when they are free.",
     obj({}), None),
    ("check_availability", "Find open meeting times on the executive's calendar. Always call before offering times.",
     obj({"meeting_type": {"type": "string", "enum": ["intro", "standard", "investor"]},
          "duration_minutes": {"type": "integer"},
          "earliest_date": {**S, "description": "YYYY-MM-DD"}, "latest_date": {**S, "description": "YYYY-MM-DD"},
          "part_of_day": {"type": "string", "enum": ["any", "morning", "afternoon", "evening"]}}),
     "Let me check the calendar."),
    ("book_meeting", "Book a meeting at a start time returned by check_availability.",
     obj({"start": {**S, "description": "Exact ISO start value from check_availability"},
          "meeting_type": {"type": "string", "enum": ["intro", "standard", "investor"]},
          "attendee_name": S, "attendee_email": S, "attendee_phone": S, "company": S,
          "topic": {**S, "description": "Short meeting topic"}}, ["start", "attendee_name"]), "Booking that now."),
    ("find_my_meeting", "Find the caller's upcoming meeting(s) with the executive, matched by caller ID, name or email.",
     obj({"name": S, "email": S}), "Let me pull that up."),
    ("reschedule_meeting", "Move the caller's existing meeting to a new time from check_availability.",
     obj({"event_id": S, "new_start": {**S, "description": "Exact ISO start value from check_availability"}},
         ["event_id", "new_start"]), "Updating that now."),
    ("take_message", "Save a complete message for the executive or a team member.",
     obj({"caller_name": S, "callback_number": S, "company": S, "reason": S, "details": S,
          "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]},
          "best_time_to_call": S,
          "for_whom": {**S, "description": "'exec' or a team member key/name (from route_call message_for)"}},
         ["caller_name", "reason"]), None),
    ("search_knowledge", "Search the company knowledge base to answer a caller's question about the company.",
     obj({"query": S}, ["query"]), None),
    ("create_followup", "Create a follow-up task with an owner and due date so nothing slips.",
     obj({"title": S, "owner": {**S, "description": "'exec' or a team member key/name"}, "due_date": {**S, "description": "YYYY-MM-DD"},
          "related_contact": S}, ["title"]), None),
    ("note_about_caller", "Quietly remember one useful fact about this caller for next time.",
     obj({"fact": S, "subject": {**S, "description": "Who the fact is about (defaults to the caller)"}}, ["fact"]), None),
    ("text_caller_info", "Text the caller one pre-approved piece of information.",
     obj({"info": {"type": "string", "enum": ["vendor_inbox", "office_address", "video_link", "website"]},
          "phone": {**S, "description": "Only if different from caller ID"}}, ["info"]), None),
]

SERVER_URL = "{{PUBLIC_BASE_URL}}/vapi/webhook"


def vapi_tool(name: str, desc: str, params: dict, filler: str | None) -> dict:
    tool = {
        "type": "function",
        "async": False,
        "function": {"name": name, "description": desc, "parameters": params},
        "server": {"url": SERVER_URL, "timeoutSeconds": 15},
    }
    if filler:
        tool["messages"] = [{"type": "request-start", "content": filler, "blocking": False},
                            {"type": "request-response-delayed", "content": "Still with you, one more moment.", "timingMilliseconds": 3000}]
    return tool


def main() -> None:
    out_dir = ROOT / "voice" / "tools"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, desc, params, filler in TOOLS:
        (out_dir / f"{name}.json").write_text(json.dumps(vapi_tool(name, desc, params, filler), indent=2) + "\n")

    # Built-in call-control tools
    (out_dir / "transfer_call.json").write_text(json.dumps({
        "type": "transferCall",
        "function": {"name": "transfer_call",
                     "description": "Transfer the live call. Only use after route_call returned transfer_exec or transfer_team."},
        "destinations": [],
        "_comment": "Empty destinations: Vapi asks the server via a transfer-destination-request, and Travis Core "
                    "returns the number chosen by route_call. The number never enters the model's context.",
        "server": {"url": SERVER_URL},
    }, indent=2) + "\n")
    (out_dir / "end_call.json").write_text(json.dumps({"type": "endCall", "function": {"name": "end_call",
        "description": "End the call after a warm goodbye, or immediately for spam."}}, indent=2) + "\n")

    prompt_md = (ROOT / "prompts" / "travis-system-prompt.md").read_text()
    system_prompt = prompt_md.split("\n---\n", 1)[1].strip()
    analysis_md = (ROOT / "prompts" / "end-of-call-analysis.md").read_text()
    blocks = analysis_md.split("```")
    summary_prompt, schema, sd_prompt, eval_prompt = blocks[1].strip(), json.loads(blocks[3].replace("json", "", 1)), blocks[5].strip(), blocks[7].strip()

    assistant = {
        "name": "TRAVIS",
        "firstMessageMode": "assistant-speaks-first",
        "firstMessage": "{{greeting}}",
        "model": {
            "provider": "anthropic",
            "model": "claude-haiku-4-5-20251001",
            "temperature": 0.3,
            "maxTokens": 300,
            "messages": [{"role": "system", "content": system_prompt}],
            "toolIds": ["<filled by scripts/deploy_vapi.py>"],
        },
        "voice": {"provider": "11labs", "voiceId": "<YOUR_VOICE_ID>", "model": "eleven_turbo_v2_5",
                  "stability": 0.55, "similarityBoost": 0.75, "style": 0.1, "useSpeakerBoost": True},
        "transcriber": {"provider": "deepgram", "model": "nova-3", "language": "en",
                        "keywords": ["TRAVIS:3"]},
        "server": {"url": SERVER_URL, "timeoutSeconds": 20},
        "serverMessages": ["tool-calls", "transfer-destination-request", "end-of-call-report", "status-update"],
        "startSpeakingPlan": {"waitSeconds": 0.4, "smartEndpointingEnabled": True},
        "stopSpeakingPlan": {"numWords": 1, "voiceSeconds": 0.2, "backoffSeconds": 1},
        "silenceTimeoutSeconds": 25,
        "maxDurationSeconds": 1200,
        "backgroundSound": "off",
        "backchannelingEnabled": False,
        "endCallMessage": "Thank you. Goodbye.",
        "voicemailMessage": "",
        "artifactPlan": {"recordingEnabled": True, "transcriptPlan": {"enabled": True}},
        "analysisPlan": {
            "summaryPlan": {"messages": [{"role": "system", "content": summary_prompt},
                                         {"role": "user", "content": "Here is the transcript:\n\n{{transcript}}\n\n"}]},
            "structuredDataPlan": {"enabled": True, "schema": schema,
                                   "messages": [{"role": "system", "content": sd_prompt},
                                                {"role": "user", "content": "Transcript:\n\n{{transcript}}\n\nSchema:\n{{schema}}"}]},
            "successEvaluationPlan": {"rubric": "PassFail",
                                      "messages": [{"role": "system", "content": eval_prompt},
                                                   {"role": "user", "content": "Transcript:\n\n{{transcript}}"}]},
        },
        "_notes": [
            "Field names follow the Vapi API at the time of writing. Check docs.vapi.ai/api-reference if a field is rejected.",
            "For latency, keep a fast model on the voice loop. The exec command channel can use a larger model.",
            "Set a server secret / credential and put the same value in VAPI_WEBHOOK_SECRET.",
        ],
    }
    (ROOT / "voice" / "vapi-assistant.json").write_text(json.dumps(assistant, indent=2) + "\n")
    print(f"Wrote {len(TOOLS) + 2} tool files and voice/vapi-assistant.json")


if __name__ == "__main__":
    main()
