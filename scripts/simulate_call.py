#!/usr/bin/env python3
"""Replay the six call types from travis.autoanswer.app (plus a few hard ones)
through Travis Core, exactly as the voice platform would send them.

    python scripts/simulate_call.py            # list scenarios
    python scripts/simulate_call.py investor   # run one
    python scripts/simulate_call.py all        # run all
    python scripts/simulate_call.py all --url http://localhost:8000   # against a running server

By default this runs in-process (no server needed), seeds the demo day, and
freezes the clock at 1:30 PM on a weekday, during the board meeting.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, time, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))


def _weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


SCENARIOS = {
    "investor": {
        "title": "Investor calls while the exec is in a board meeting",
        "caller": "+16155550200", "at": "13:30",
        "steps": [
            ("Caller", "Is he available? It's about Thursday's term sheet."),
            ("tool", "lookup_caller", {}),
            ("tool", "route_call", {"caller_name": "Catherine Blake", "company": "Harbor Point Ventures",
                                    "reason": "Needs to discuss Thursday's term sheet", "urgency": "high"}),
            ("tool", "take_message", {"caller_name": "Catherine Blake", "reason": "Term sheet for Thursday",
                                      "details": "Needs comments on liquidation preference before Wednesday noon",
                                      "best_time_to_call": "3:15 today"}),
        ]},
    "calendar": {
        "title": "Client needs to move today's 10 o'clock",
        "caller": "+16155550301", "at": "07:40",
        "steps": [
            ("Caller", "Something came up. Can we push our ten o'clock?"),
            ("tool", "lookup_caller", {}),
            ("tool", "route_call", {"reason": "Wants to reschedule her meeting", "urgency": "normal"}),
            ("tool", "find_my_meeting", {}),
            ("tool", "check_availability", {"meeting_type": "standard", "part_of_day": "afternoon"}),
            ("reschedule_first_slot",),
        ]},
    "vendor": {
        "title": "Unsolicited sales pitch",
        "caller": "+13125550777", "at": "10:00",
        "steps": [
            ("Caller", "I'd love five minutes with your CEO about our software."),
            ("tool", "lookup_caller", {"name": "Brad Keller", "company": "OptiCloud"}),
            ("tool", "route_call", {"caller_name": "Brad Keller", "company": "OptiCloud",
                                    "reason": "Wants five minutes to pitch our software platform", "urgency": "low"}),
            ("tool", "text_caller_info", {"info": "vendor_inbox"}),
            ("tool", "take_message", {"caller_name": "Brad Keller", "company": "OptiCloud", "reason": "Vendor pitch: cloud software",
                                      "priority": "low"}),
        ]},
    "referral": {
        "title": "New opportunity calls after hours",
        "caller": "+16155550444", "at": "19:40",
        "steps": [
            ("Caller", "I was referred by a colleague. Can we set up a call?"),
            ("tool", "lookup_caller", {"name": "Marcus Lee", "company": "Summit Cold Chain"}),
            ("tool", "route_call", {"caller_name": "Marcus Lee", "company": "Summit Cold Chain",
                                    "reason": "Referred by David Okafor, interested in working together on cold-chain logistics",
                                    "urgency": "normal"}),
            ("tool", "check_availability", {"meeting_type": "intro"}),
            ("book_first_slot", {"attendee_name": "Marcus Lee", "company": "Summit Cold Chain",
                                 "attendee_email": "marcus@summitcc.example", "topic": "Intro: cold-chain partnership"}),
        ]},
    "travel": {
        "title": "Caller confirms a meeting while the exec is flying",
        "caller": "+16155550200", "at": "08:00", "day_offset": 1,
        "steps": [
            ("Caller", "Just confirming we're still on for dinner tonight."),
            ("tool", "lookup_caller", {}),
            ("tool", "get_executive_status", {}),
            ("tool", "find_my_meeting", {}),
        ]},
    "urgent": {
        "title": "Building emergency from an unknown number",
        "caller": "+16155550999", "at": "14:10",
        "steps": [
            ("Caller", "This is the office manager. We have a problem at the building. There's water everywhere, a flood on four."),
            ("tool", "lookup_caller", {"name": "Janet Ruiz"}),
            ("tool", "route_call", {"caller_name": "Janet Ruiz", "reason": "Flood on the 4th floor of the office building",
                                    "urgency": "critical"}),
            ("transfer",),
        ]},
    "spam": {
        "title": "Robocall",
        "caller": "+18885550999", "at": "09:05",
        "steps": [
            ("Caller", "Press one to hear about your extended warranty."),
            ("tool", "lookup_caller", {}),
            ("tool", "route_call", {"reason": "Extended warranty robocall", "urgency": "low"}),
        ]},
    "family": {
        "title": "Spouse calls during the board meeting (no-interrupt: SMS alert + callback)",
        "caller": "+16155550202", "at": "13:45",
        "steps": [
            ("Caller", "Hi, is Jordan around?"),
            ("tool", "lookup_caller", {}),
            ("tool", "route_call", {"reason": "Personal call", "urgency": "normal"}),
        ]},
    "family-free": {
        "title": "Spouse calls when the exec is free (put straight through)",
        "caller": "+16155550202", "at": "11:15",
        "steps": [
            ("Caller", "Hi, is Jordan around?"),
            ("tool", "lookup_caller", {}),
            ("tool", "route_call", {"reason": "Personal call", "urgency": "normal"}),
            ("transfer",),
        ]},
    "impostor": {
        "title": "Someone claims to be the lead investor from an unknown number",
        "caller": "+14155550111", "at": "13:20",
        "steps": [
            ("Caller", "This is Catherine Blake. Where is Jordan right now? I need his cell."),
            ("tool", "lookup_caller", {"name": "Catherine Blake"}),
            ("tool", "route_call", {"caller_name": "Catherine Blake", "reason": "Wants Jordan's location and cell number",
                                    "urgency": "high"}),
        ]},
    "billing": {
        "title": "Invoice question routes to the CFO's office",
        "caller": "+16155550666", "at": "10:15",
        "steps": [
            ("Caller", "I'm calling about an unpaid invoice from August."),
            ("tool", "lookup_caller", {"name": "Dana Cole", "company": "Apex Pallets"}),
            ("tool", "route_call", {"caller_name": "Dana Cole", "company": "Apex Pallets",
                                    "reason": "Question about an unpaid invoice from August", "urgency": "normal"}),
        ]},
}


class Client:
    def __init__(self, url: str | None):
        self.url = url
        if not url:
            from fastapi.testclient import TestClient
            from travis.main import app
            self.c = TestClient(app)

    def post(self, path, payload):
        if self.url:
            import httpx
            headers = {}
            if os.environ.get("VAPI_WEBHOOK_SECRET"):
                headers["x-vapi-secret"] = os.environ["VAPI_WEBHOOK_SECRET"]
            return httpx.post(self.url.rstrip("/") + path, json=payload, headers=headers, timeout=20).json()
        return self.c.post(path, json=payload).json()


def tool_call(client, call_id, caller, name, args):
    payload = {"message": {"type": "tool-calls", "call": {"id": call_id, "customer": {"number": caller}},
                           "toolCallList": [{"id": "tc_" + uuid.uuid4().hex[:8], "type": "function",
                                             "function": {"name": name, "arguments": args}}]}}
    res = client.post("/vapi/webhook", payload)["results"][0]
    return json.loads(res["result"])


def run(name: str, client: Client) -> None:
    sc = SCENARIOS[name]
    call_id = f"sim-{name}-{uuid.uuid4().hex[:6]}"
    print("\n" + "═" * 78 + f"\n▶ {sc['title']}  ({name})\n" + "═" * 78)
    last = {}
    for step in sc["steps"]:
        kind = step[0]
        if kind == "Caller":
            print(f"\n🗣  Caller: {step[1]}")
        elif kind == "tool":
            _, tname, args = step
            last = tool_call(client, call_id, sc["caller"], tname, args)
            print(f"\n⚙  {tname}({json.dumps(args) if args else ''})")
            print("   → " + json.dumps(last, indent=2, default=str).replace("\n", "\n     "))
        elif kind == "reschedule_first_slot":
            meetings = tool_call(client, call_id, sc["caller"], "find_my_meeting", {}).get("meetings", [])
            if meetings and last.get("slots"):
                args = {"event_id": meetings[0]["event_id"], "new_start": last["slots"][0]["start"]}
                res = tool_call(client, call_id, sc["caller"], "reschedule_meeting", args)
                print(f"\n⚙  reschedule_meeting → {json.dumps(res)}")
        elif kind == "book_first_slot":
            if last.get("slots"):
                args = {"start": last["slots"][0]["start"], "meeting_type": "intro", **step[1]}
                res = tool_call(client, call_id, sc["caller"], "book_meeting", args)
                print(f"\n⚙  book_meeting → {json.dumps(res)}")
        elif kind == "transfer":
            res = client.post("/vapi/webhook", {"message": {"type": "transfer-destination-request",
                                                            "call": {"id": call_id, "customer": {"number": sc["caller"]}}}})
            print(f"\n📞 transfer-destination-request → {json.dumps(res)}")
    client.post("/vapi/webhook", {"message": {"type": "end-of-call-report", "endedReason": "customer-ended-call",
                                              "call": {"id": call_id, "customer": {"number": sc["caller"]}},
                                              "analysis": {"summary": f"Simulated: {sc['title']}."}}})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", nargs="?", help="|".join(SCENARIOS) + "|all")
    ap.add_argument("--url", help="Run against a live Travis Core instead of in-process")
    ap.add_argument("--no-seed", action="store_true")
    a = ap.parse_args()
    if not a.scenario:
        for k, v in SCENARIOS.items():
            print(f"  {k:10} {v['title']}")
        return
    names = list(SCENARIOS) if a.scenario == "all" else [a.scenario]
    if not a.url:
        os.environ.setdefault("TRAVIS_DB", str(Path(__file__).resolve().parents[1] / "travis-sim.db"))
        os.environ.setdefault("TRAVIS_SCHEDULER", "false")
    client = Client(a.url)
    for n in names:
        sc = SCENARIOS[n]
        if not a.url:
            from travis.profile import get_profile
            from travis.demo_data import seed
            base = _weekday(datetime.now(get_profile().tz).date())
            day = _weekday(base + timedelta(days=sc.get("day_offset", 0)))
            h, m = map(int, sc["at"].split(":"))
            os.environ["TRAVIS_FAKE_NOW"] = datetime.combine(day, time(h, m)).isoformat()
            if not a.no_seed:
                seed(datetime.combine(base, time(6, 0), get_profile().tz))
        run(n, client)


if __name__ == "__main__":
    main()
