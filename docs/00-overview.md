# 00 · Overview: what TRAVIS is

TRAVIS (Task Routing and Automated Virtual Intelligence System) is an AI chief of staff for one executive. He answers the executive's phone 24/7, decides who gets through, manages the calendar, takes messages good enough to act on, follows up, and briefs the executive every morning. The executive talks to him by text.

He is not an IVR ("press 1 for sales"), not a shared receptionist for a whole company, and not a booking link. The difference is **judgment backed by rules**: TRAVIS knows who matters to this one executive, what counts as urgent, which hours are sacred, and what must never be said.

## The promise (from the product page)

| Promise | How this repo delivers it |
|---|---|
| "I answer on the first ring, every time." | Voice platform assistant (`voice/`), always on |
| "I work nights, weekends and holidays." | Same logic runs 24/7; after-hours behavior is a rule, not an outage |
| "I handle several calls at once." | Each call is an independent session on the voice platform |
| "I speak multiple languages." | Multilingual transcriber + prompt rule to switch languages |
| "I remain composed with every caller, even at 3 AM." | Persona (`prompts/persona-and-voice.md`) + low temperature |
| "I deliver a briefing every morning." | `server/travis/briefing.py`, sent 6:45 AM |
| "I manage and protect your calendar." | `calendar/availability.py` enforces buffers, protected blocks, caps |
| "I schedule, confirm and reschedule meetings." | `check_availability` / `book_meeting` / `reschedule_meeting` tools + SMS confirmations + evening-before reminders |
| "I route every call to you, your team or voicemail, by priority." | `routing.py` decision matrix + `transfer_call` |
| "I take detailed messages and send you a summary." | `take_message` + end-of-call summary |
| "I remember what you tell me." | `memories` table, `remember` by text, `note_about_caller` on calls |
| "I assign follow-ups to the right person automatically." | `create_followup` + team routing by topic |
| "I greet every client by name." | `lookup_caller` against VIP list + contacts |
| "I answer questions about your company." | `search_knowledge` over your knowledge base |
| "I learn your people, priorities and preferences." | Executive profile YAML + onboarding process (`docs/11`) |
| "I follow up so nothing slips." | Follow-ups table, briefing "Follow-ups due" |
| "I call, text and chat." | Voice + SMS (both directions); web chat is on the roadmap |
| "I escalate urgent matters straight to you." | Urgency assessment + critical path transfer + SMS alert |
| "Already have an assistant and a strong team? Keep them." | `team:` in the profile; topic routing hands work to humans |

## Design principles

1. **The model gathers facts; code makes decisions.** The LLM is great at conversation and bad at consistently applying 40 rules. So TRAVIS asks who and why, then calls `route_call`, and deterministic code in Travis Core decides transfer vs message vs booking. You can unit-test it, audit it, and change it without re-prompting.
2. **Rules live in config, not in the prompt.** One system prompt serves every executive. Their VIPs, hours, blocks and team live in `config/<exec>.yaml`.
3. **Least privilege toward callers.** The model never sees the executive's phone number, other attendees, or meeting titles. Transfer numbers are resolved server-side. Status is pre-written in caller-safe language.
4. **Every call produces a record and an owner.** Calls, messages, actions and follow-ups are all logged; the briefing makes open items impossible to miss.
5. **Fail toward a great message.** If anything breaks, TRAVIS takes a detailed message and marks it high priority. A caller should never hear an error.
6. **Honest AI.** TRAVIS says he's an AI whenever asked.

## What you need

| Layer | Reference choice | Alternatives |
|---|---|---|
| Phone number + voice runtime | Vapi | Retell, Votel.ai, Bland, ElevenLabs Agents, Synthflow, LiveKit/Pipecat (self-hosted) |
| Speech-to-text | Deepgram Nova-3 | AssemblyAI, Gladia, platform default |
| LLM (voice loop) | A fast model (Claude Haiku class, GPT-4.1-mini class) | Any low-latency tool-calling model |
| LLM (exec text channel) | Claude Sonnet class | Any strong tool-calling model |
| Text-to-speech | ElevenLabs | Cartesia, Rime, OpenAI TTS, PlayHT |
| Backend ("Travis Core") | This repo (Python/FastAPI) | n8n / Make workflows (see `docs/13`) |
| Calendar | Google Calendar | Microsoft 365 (adapter stub), Cal.com, GoHighLevel calendars |
| SMS | Twilio | Telnyx, platform-native SMS, LeadConnector |
| Email | Any SMTP | Resend, Postmark, SES, Gmail API |
| Database | SQLite | Postgres (schema is compatible) |
| Hosting | Any container host with HTTPS | Railway, Render, Fly.io, a VPS with Caddy |

## Build time estimate

| Phase | First build | Each new executive after that |
|---|---|---|
| Accounts, number, local demo | 2–3 hours | n/a |
| Voice assistant + tools live on a test number | 1 day | 15 minutes |
| Calendar + SMS + email wired | 1 day | 30 minutes |
| Onboarding (profile, VIPs, knowledge base) | half day | 2–4 hours |
| QA with the 30-call eval set | half day | 1–2 hours |
| **Total** | **~4 days** | **~1 day including the client interview** |
