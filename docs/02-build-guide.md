# 02 · Build guide: TRAVIS from zero to live, in 12 phases

Each phase ends with a **checkpoint**. Don't move on until it passes.

---

## Phase 1 · Accounts and tools (1–2 hours)

Create:

- [ ] A voice platform account (reference: Vapi, docs.vapi.ai). Add a payment method; you'll buy a number.
- [ ] An ElevenLabs account (or use your platform's built-in voices).
- [ ] Twilio: account, a local number with SMS, and **A2P 10DLC brand + campaign registration** (US). Registration takes days; start now. Campaign type "Customer care / account notifications", describe it as "Assistant texts for meeting confirmations and messages for [company]".
- [ ] A Google Cloud project with the Calendar API enabled (Phase 5).
- [ ] An SMTP sender (Workspace/365 app password, Resend, Postmark…).
- [ ] An Anthropic API key for the executive text channel (optional; the rule-based fallback works without it).
- [ ] A host that gives you HTTPS (Railway, Render, Fly.io, or a VPS with Caddy). For development, `cloudflared tunnel` or `ngrok` works.

**Checkpoint:** you can log in to each and you have API keys in a password manager.

---

## Phase 2 · Run the reference locally in demo mode (30 minutes)

```bash
git clone https://github.com/qexa/travis-ai-chief-of-staff.git && cd travis-ai-chief-of-staff
python -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
cp .env.example .env
python scripts/seed_demo.py
pytest server/tests -q                       # 40+ tests, all green
python scripts/simulate_call.py all          # replays every call type from the site
python scripts/send_briefing.py --print
uvicorn travis.main:app --app-dir server --reload
```

Open `http://localhost:8000/docs` for the interactive API.

Try the text channel without a phone:

```bash
curl -s localhost:8000/exec/command -H 'content-type: application/json' -d '{"text":"move my 10am to thursday"}'
```

**Checkpoint:** tests pass; `simulate_call.py investor` shows `offer_callback` with a 3:15 callback; the briefing prints.

---

## Phase 3 · Write the executive profile (1–2 hours per exec)

Copy `config/executive.example.yaml` to `config/<exec-slug>.yaml` and point `TRAVIS_PROFILE` at it. Fill it in using the interview in `docs/11-client-onboarding.md`. The fields that matter most:

1. `executive.mobile` and `command_numbers`: transfers and the text channel.
2. `vips`: every person who should be greeted by name or put through. Get real caller-ID numbers.
3. `team`: who handles what, so TRAVIS can route billing to finance and press to comms.
4. `calendar`: meeting hours, buffers, protected blocks, max meetings, no-interrupt keywords.
5. `confidential`: what must never be said.

Validate:

```bash
python -c "import sys; sys.path.insert(0,'server'); from travis.profile import get_profile; p=get_profile(); print(p.exec['name'], len(p.data['vips']), 'VIPs')"
python scripts/simulate_call.py all
```

**Checkpoint:** the simulations route the way the executive would expect. Walk the exec (or their EA) through the output.

---

## Phase 4 · Knowledge base (1–2 hours)

Create `knowledge/<exec-slug>/` with markdown files using `knowledge/templates/`. One `## Heading` per topic; keep sections short and factual. Mark anything callers must never hear with `[CONFIDENTIAL]` or `[INTERNAL]` in the heading; those sections are only searchable from the executive's text channel.

Set `TRAVIS_KNOWLEDGE_DIR=knowledge/<exec-slug>`.

**Checkpoint:** `curl localhost:8000/tools/search_knowledge -H 'content-type: application/json' -d '{"query":"office hours"}'` returns the right section.

---

## Phase 5 · Calendar (1–2 hours)

1. Google Cloud Console → enable **Google Calendar API** → OAuth consent screen (Internal if Workspace, else External + test user) → Credentials → **OAuth client ID (Desktop app)**.
2. `GOOGLE_CLIENT_ID=… GOOGLE_CLIENT_SECRET=… python scripts/google_oauth.py`, sign in as the executive (or the EA account with delegated access to the exec's calendar), paste the code.
3. In `.env`: `CALENDAR_BACKEND=google`, the three Google values, and `GOOGLE_CALENDAR_ID` (usually `primary`, or the exec's email if using a delegate).
4. Mark travel events so TRAVIS knows: titles containing "Flight" are detected automatically; for anything else, set the private extended property `travis_kind=travel` (or add a word like "Flight" to the title).

Microsoft 365: implement `calendar/base.py`'s five methods against Microsoft Graph (`/me/calendarView`, `/me/events`). The interface is intentionally small.

**Checkpoint:** `curl -X POST localhost:8000/exec/command -d '{"text":"schedule"}' -H 'content-type: application/json'` lists the real calendar.

---

## Phase 6 · SMS and email (1 hour + 10DLC wait)

1. Put Twilio SID, auth token and the SMS number in `.env`.
2. In Twilio → Phone Numbers → your number → Messaging → "A message comes in": `POST https://<your-host>/sms/inbound`.
3. Keep `TWILIO_VALIDATE_SIGNATURE=true` and set `PUBLIC_BASE_URL` to the exact public URL Twilio calls, or signatures won't match.
4. Add SMTP settings.

**Checkpoint:** text "schedule" from the executive's phone and get the day back. Text from any other phone and get "I've passed your message along."

> Tip: use a different number for SMS than the voice line only if your voice platform can't do SMS on the same number. One number for everything is a better experience.

---

## Phase 7 · Deploy Travis Core (1 hour)

```bash
docker compose up -d --build        # or deploy the Dockerfile to Railway/Render/Fly
curl https://<your-host>/health
```

Production `.env` must have: `VAPI_WEBHOOK_SECRET`, `TRAVIS_ADMIN_TOKEN`, `PUBLIC_BASE_URL`, real calendar, SMS and SMTP. Keep **one worker** (see `docs/01` scaling notes). Mount `/data` on a persistent volume and back it up nightly.

**Checkpoint:** `/health` shows `calendar: google, sms: true, email: true`.

---

## Phase 8 · Create the voice assistant (1–2 hours)

1. Pick the voice (`prompts/persona-and-voice.md`). Note its ID.
2. Review `prompts/travis-system-prompt.md`. If you change tools, edit `scripts/build_voice_config.py` and re-run it.
3. Deploy tools + assistant:

```bash
export VAPI_API_KEY=… PUBLIC_BASE_URL=https://<your-host> VAPI_WEBHOOK_SECRET=…
python scripts/deploy_vapi.py --voice-id <voice_id> --dry-run   # inspect
python scripts/deploy_vapi.py --voice-id <voice_id>
```

4. Put the printed id in `VAPI_ASSISTANT_ID` and restart Core.

Manual alternative (dashboard): create each tool from `voice/tools/*.json` (Tools → Create → Function; paste name, description, parameters; server URL `https://<your-host>/vapi/webhook`), then create the assistant and paste the settings from `voice/vapi-assistant.json`.

**Checkpoint:** "Talk to assistant" in the dashboard. Say "Hi, it's Brad from OptiCloud, I'd love five minutes about our software." TRAVIS should screen you and offer the vendor inbox text.

---

## Phase 9 · Phone number and routing (30 minutes)

1. Buy a number in the voice platform (or import your Twilio number).
2. **Dynamic mode (recommended):** `python scripts/deploy_vapi.py --voice-id … --phone-number-id <id> --dynamic`. The number now calls Core's `assistant-request` on every call; Core returns the assistant plus live variables (time, exec status, greeting). This is what makes "Good evening" correct at 9 PM and lets TRAVIS know the exec is in a meeting before the caller asks.
3. Forwarding the executive's existing line: set the carrier's **conditional call forwarding** (busy / no answer / unreachable) to TRAVIS's number, or forward all calls. Typical US codes: Verizon `*71` + number (no-answer/busy), cancel with `*73`; AT&T and T-Mobile (GSM) `**004*+1NUMBER#` sets all conditional forwarding (busy `**67*`, no answer `**61*`, unreachable `**62*`), cancel with `##004#`. Confirm with your carrier, especially on business plans. Now TRAVIS picks up whatever the exec doesn't.
4. **Transfers when the exec's line forwards to TRAVIS:** transferring back to the exec's mobile would loop. Use a second "direct" number for transfers (a separate SIM, a Google Voice line, or a softphone like the Vapi/Twilio client) and put that in `executive.mobile`.

**Checkpoint:** call from a VIP number listed in the profile and hear your name.

---

## Phase 10 · The morning briefing and reminders (15 minutes)

- `briefing.send_at`, `days`, `channels` in the profile. The in-process scheduler sends it (`TRAVIS_SCHEDULER=true`).
- If you run more than one process, disable it and call `POST /briefing/run?send=true` with the admin token from cron at the same time.
- `reminders.send_at` texts external attendees the evening before.

**Checkpoint:** set `send_at` two minutes from now, watch it arrive, reset it.

---

## Phase 11 · QA with the eval set (2–4 hours)

Run every scenario in `evals/test-calls.md` by phone, from the right kind of number (VIP numbers need a VIP-listed phone or a temporary profile entry). Score each against its pass criteria. Also run `evals/red-team.md`. Fix, re-deploy, re-run anything that failed. Details in `docs/10-testing-and-qa.md`.

**Checkpoint:** 30/30 pass, zero discretion failures, every call produced a summary.

---

## Phase 12 · Go live and hypercare (first 2 weeks)

1. Tell the executive exactly what TRAVIS will and won't do (one page; template in `docs/11`).
2. Turn on forwarding.
3. Days 1–3: read every transcript. Days 4–14: read all high/critical and any call under 20 seconds (hang-ups signal problems).
4. Weekly: tune VIPs, protected blocks, knowledge base; add phrases that confused the transcriber to the transcriber `keywords`.
5. Monthly: re-run the eval set after any prompt or model change.

**Checkpoint:** the executive stops checking their voicemail.
