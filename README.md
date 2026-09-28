# Task Routing and Automated Virtual Intelligence System

T.R.A.V.I.S. Open-Source AI Chief of Staff Blueprint

**Task Routing and Automated Virtual Intelligence System**

> "You run the company. TRAVIS handles everything else."

TRAVIS is an always-on AI executive assistant that answers every call on the first ring, screens and routes callers by priority, manages and protects an executive's calendar, sends a morning briefing, remembers what it's told, and follows up so nothing slips. This repository is a complete, free blueprint for building your own TRAVIS-style assistant from scratch.

It is the open reference build behind the production service at [travis.autoanswer.app](https://travis.autoanswer.app), published by [AutoAnswer.app](https://autoanswer.app) / [Qexa Technology](https://qexa.com). Fork it, rename him, give him your own voice.

---

## What you get

| Folder | What's in it |
|---|---|
| [`docs/`](docs/) | The full blueprint: architecture, a 12-phase build guide, call-handling playbooks, routing matrix, morning briefing spec, memory model, security and compliance, testing, client onboarding, operations, cost model |
| [`prompts/`](prompts/) | Production-grade system prompt, persona guide, call-scenario scripts, briefing and summary prompts |
| [`voice/`](voice/) | Ready-to-import voice-platform assistant config (Vapi format) and every tool/function schema TRAVIS uses |
| [`config/`](config/) | The executive profile: VIP list, routing rules, calendar protection rules, briefing settings. One YAML file per client. |
| [`server/`](server/) | **Travis Core**: a working Python/FastAPI reference backend that implements every tool: caller lookup, priority routing, calendar availability, booking, rescheduling, messages, memory, follow-ups, the SMS command channel and the morning briefing. Tested. |
| [`database/`](database/) | SQL schema (SQLite/Postgres compatible) |
| [`knowledge/`](knowledge/) | Knowledge-base templates plus a fully worked fictional example company |
| [`evals/`](evals/) | 30 scripted test calls with pass criteria, to QA a build before it takes live calls |
| [`scripts/`](scripts/) | Deploy the assistant to Vapi, simulate calls locally, send a briefing, seed demo data |

## The 60-second picture

```
 Caller ──► Phone number ──► Voice platform (Vapi / Retell / Votel.ai)
                                  │   STT ─► LLM (TRAVIS prompt) ─► TTS
                                  │
                         tool calls (webhook)
                                  ▼
                        ┌──────────────────────┐
                        │     Travis Core      │  FastAPI (this repo)
                        │  routing • calendar  │
                        │  memory • messages   │
                        │  follow-ups • brief  │
                        └─────────┬────────────┘
             ┌────────────┬───────┴──────┬──────────────┐
        Google/MS365    Twilio SMS     Email (SMTP/     Database
         Calendar      (exec commands   Resend/Gmail)   (contacts,
                        + alerts)                        memory, log)
```

1. A call comes in. TRAVIS answers in under a ring and calls `lookup_caller`.
2. Travis Core matches the number against the VIP list and contacts and returns a **tier** (VIP, Inner Circle, Known, New Opportunity, Vendor, Spam) and the routing instruction.
3. TRAVIS handles the call: transfers urgent matters, books or moves meetings, takes detailed messages, deflects pitches politely.
4. Every call ends with a summary texted or emailed to the executive, prioritized.
5. At 6:45 AM, the executive gets the **Systems Briefing**: overnight calls, today's meetings, who needs a reply, spam blocked.
6. The executive can text TRAVIS anything ("move my 2pm to Friday", "who called about the term sheet?") and TRAVIS acts on it.

## Quick start (local, 10 minutes)

```bash
git clone https://github.com/qexa/travis-ai-chief-of-staff.git
cd travis-ai-chief-of-staff
python -m venv .venv && source .venv/bin/activate
pip install -r server/requirements.txt
cp .env.example .env                  # works as-is in demo mode, no keys needed
python scripts/seed_demo.py           # loads the fictional exec "Jordan Hale"
uvicorn travis.main:app --app-dir server --reload
python scripts/simulate_call.py investor   # watch TRAVIS route an investor call
python scripts/send_briefing.py --print    # print tomorrow's morning briefing
pytest server/tests -q
```

Then follow [`docs/02-build-guide.md`](docs/02-build-guide.md) to connect a real phone number, calendar and SMS.

## Read in this order

1. [`docs/00-overview.md`](docs/00-overview.md): what TRAVIS is and the design principles
2. [`docs/01-architecture.md`](docs/01-architecture.md): components, data flows, sequence diagrams
3. [`docs/02-build-guide.md`](docs/02-build-guide.md): the 12-phase step-by-step build
4. [`docs/03-call-playbooks.md`](docs/03-call-playbooks.md): exactly how each call type is handled
5. [`docs/04-routing-and-priority.md`](docs/04-routing-and-priority.md): the tiers and decision matrix
6. [`docs/05-calendar-management.md`](docs/05-calendar-management.md): protection rules and scheduling logic
7. [`docs/06-morning-briefing.md`](docs/06-morning-briefing.md): the daily brief
8. [`docs/07-memory-and-knowledge.md`](docs/07-memory-and-knowledge.md): what TRAVIS remembers and how
9. [`docs/08-exec-command-channel.md`](docs/08-exec-command-channel.md): "Ask TRAVIS anything" by text
10. [`docs/09-security-privacy-compliance.md`](docs/09-security-privacy-compliance.md): read before going live
11. [`docs/10-testing-and-qa.md`](docs/10-testing-and-qa.md)
12. [`docs/11-client-onboarding.md`](docs/11-client-onboarding.md): the "trained on your business" process
13. [`docs/12-operations-and-costs.md`](docs/12-operations-and-costs.md): monitoring, costs, pricing math
14. [`docs/13-platform-notes.md`](docs/13-platform-notes.md): Vapi, Retell, Votel.ai, Bland, ElevenLabs Agents
15. [`docs/14-roadmap.md`](docs/14-roadmap.md)

## Design principles

- **Composed, never flustered.** Same calm tone at 3 AM as at 3 PM.
- **Protect the executive's time first, the caller's dignity always.** Nobody gets brushed off; very few get through.
- **Never invent.** If TRAVIS doesn't know, he takes a message. He never makes commitments on the executive's behalf beyond what the rules allow.
- **Every call produces a record.** No call ends without a summary and an owner for the next step.
- **The human team stays.** TRAVIS works alongside existing assistants and routes work to them.
- **Rules live in config, not in the prompt.** The prompt teaches judgment; YAML holds the facts, so one prompt serves every client.

## License

MIT. Use it commercially, rebrand it, sell it. Attribution appreciated, not required. See [LICENSE](LICENSE).

"TRAVIS" as a name is used here for the reference persona. If you run it as a commercial service, pick your own name and voice.

## Disclaimer

This is a reference implementation. Call recording, AI disclosure, telemarketing and privacy rules vary by state and country. Read [`docs/09-security-privacy-compliance.md`](docs/09-security-privacy-compliance.md) and talk to a lawyer before taking live calls for a client. Nothing here is legal advice.
