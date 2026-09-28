#!/usr/bin/env python3
"""Create (or update) TRAVIS's tools and assistant in Vapi, and point a phone number at him.

    export VAPI_API_KEY=...  PUBLIC_BASE_URL=https://travis.yourdomain.com  VAPI_WEBHOOK_SECRET=...
    python scripts/deploy_vapi.py --voice-id <elevenlabs_voice_id> [--phone-number-id <vapi_phone_id>]

Idempotent: tools and the assistant are matched by name and updated in place.
Writes the assistant id to .vapi-state.json; put it in VAPI_ASSISTANT_ID.

API shapes follow docs.vapi.ai at the time of writing. If Vapi rejects a field,
check the API reference and adjust voice/vapi-assistant.json or this script.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.vapi.ai"


def fill(obj, base_url: str, secret: str):
    """Replace {{PUBLIC_BASE_URL}} and attach the webhook secret to every server block."""
    if isinstance(obj, dict):
        out = {k: fill(v, base_url, secret) for k, v in obj.items() if not k.startswith("_")}
        if "server" in out and isinstance(out["server"], dict) and secret:
            out["server"]["headers"] = {"x-vapi-secret": secret}
        return out
    if isinstance(obj, list):
        return [fill(v, base_url, secret) for v in obj]
    if isinstance(obj, str):
        return obj.replace("{{PUBLIC_BASE_URL}}", base_url.rstrip("/"))
    return obj


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--phone-number-id", help="Vapi phone number id to route to TRAVIS")
    ap.add_argument("--dynamic", action="store_true",
                    help="Point the phone number at the server URL (assistant-request) instead of a fixed assistant, "
                         "so Travis Core injects live variables (time, exec status) on every call. Recommended.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    key, base, secret = os.environ.get("VAPI_API_KEY"), os.environ.get("PUBLIC_BASE_URL"), os.environ.get("VAPI_WEBHOOK_SECRET", "")
    if not (key and base) and not a.dry_run:
        sys.exit("Set VAPI_API_KEY and PUBLIC_BASE_URL (your public https URL for Travis Core).")
    base = base or "https://example.com"
    if not secret:
        print("⚠  VAPI_WEBHOOK_SECRET is empty. Anyone who finds your server URL could call your tools. Set it.")
    h = {"Authorization": f"Bearer {key}"}
    c = httpx.Client(timeout=30, headers=h)

    existing_tools = {} if a.dry_run else {t.get("function", {}).get("name"): t for t in c.get(f"{API}/tool").json()}
    tool_ids = []
    for path in sorted((ROOT / "voice" / "tools").glob("*.json")):
        spec = fill(json.loads(path.read_text()), base, secret)
        name = spec.get("function", {}).get("name")
        if a.dry_run:
            print(f"[dry-run] tool {name}")
            continue
        if name in existing_tools:
            tid = existing_tools[name]["id"]
            body = {k: v for k, v in spec.items() if k != "type"}
            r = c.patch(f"{API}/tool/{tid}", json=body)
        else:
            r = c.post(f"{API}/tool", json=spec)
        r.raise_for_status()
        tool_ids.append(r.json()["id"])
        print(f"✓ tool {name} → {r.json()['id']}")

    assistant = fill(copy.deepcopy(json.loads((ROOT / "voice" / "vapi-assistant.json").read_text())), base, secret)
    assistant["voice"]["voiceId"] = a.voice_id
    assistant["model"]["toolIds"] = tool_ids
    if a.dry_run:
        print(json.dumps(assistant, indent=2)[:1500] + "\n…")
        return

    found = next((x for x in c.get(f"{API}/assistant").json() if x.get("name") == assistant["name"]), None)
    r = c.patch(f"{API}/assistant/{found['id']}", json=assistant) if found else c.post(f"{API}/assistant", json=assistant)
    r.raise_for_status()
    aid = r.json()["id"]
    print(f"✓ assistant TRAVIS → {aid}")
    (ROOT / ".vapi-state.json").write_text(json.dumps({"assistant_id": aid, "tool_ids": tool_ids}, indent=2))

    if a.phone_number_id:
        if a.dynamic:
            body = {"assistantId": None, "server": {"url": f"{base.rstrip('/')}/vapi/webhook",
                                                    **({"headers": {"x-vapi-secret": secret}} if secret else {})}}
        else:
            body = {"assistantId": aid}
        c.patch(f"{API}/phone-number/{a.phone_number_id}", json=body).raise_for_status()
        print(f"✓ phone number {a.phone_number_id} → {'server (assistant-request)' if a.dynamic else 'assistant'}")
    print(f"\nNext: set VAPI_ASSISTANT_ID={aid} in your .env and restart Travis Core.")


if __name__ == "__main__":
    main()
