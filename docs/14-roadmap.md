# 14 · Roadmap and contribution ideas

Good first issues are marked ⭐.

## Near term
- ⭐ Microsoft 365 calendar backend (`calendar/microsoft.py`, Graph API)
- ⭐ `scripts/export_or_delete_contact.py` for privacy requests (all rows for a phone number)
- ⭐ Transcript retention job (purge transcripts older than N days)
- ⭐ `/admin` web dashboard: calls, messages, follow-ups, contacts (promote/demote tiers), memories
- Warm transfer mode (exec hears a 1-sentence brief before connecting)
- Exec voice mode: exec calls in, spoken PIN, "read my messages", "what's next", "move my 2pm"
- Spoken passphrase verification for inner-circle transfers (anti-spoofing)
- Personal-calendar free/busy overlay (block time without reading it)
- Redis-backed `CALL_STATE` for multi-worker deployments

## Medium term
- Email triage: read the exec's inbox (Gmail/Graph), draft replies, include "emails needing you" in the briefing
- Outbound calls on the exec's behalf ("call the Four Seasons and move dinner to 8"), with TCPA-compliant consent handling
- Web chat widget on the exec's site using the same tools
- Travel assistant: parse confirmation emails into travel events automatically
- Meeting prep: 10 minutes before each meeting, text a one-paragraph brief on the attendee (from memories + past calls)
- Weekly review: Friday 4 PM summary of the week, open follow-ups by owner
- Multi-tenant mode: many executives, one deployment, tenant from the dialed number

## Long term
- Delegated negotiation within limits the exec sets (e.g. reschedule within a window without asking)
- Team-wide TRAVIS: one assistant per leader, shared routing between them
- On-prem / VPC deployment guide for regulated industries

## Contributing

1. Fork, branch, and make the change with a test.
2. `pytest server/tests -q && python scripts/build_voice_config.py && python scripts/simulate_call.py all`
3. Open a PR describing the scenario it fixes or enables. Keep executive data fictional.
