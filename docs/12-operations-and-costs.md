# 12 · Operations and costs

## Monitoring

| What | How |
|---|---|
| Core is up | `GET /health` from an uptime monitor (Better Stack, UptimeRobot) every minute; alert by SMS |
| Webhook errors | Voice platform dashboard → failed tool calls; alert on > 2% |
| Tool failures | Core logs `tool X failed` with stack traces; ship logs (Railway/Render built-ins, or Vector → Better Stack) |
| Notification failures | `SELECT * FROM outbox WHERE status='failed'` daily; alert on any |
| Calendar auth expired | Google refresh token revoked → every calendar tool errors; alert on the first `invalid_grant` |
| Spend | Platform spend alerts at 50/80/100% of expected monthly minutes |
| Quality | Weekly: read all high/critical transcripts + a random 10; monthly: re-run the eval set |

## Backups

SQLite: `sqlite3 /data/travis.db ".backup '/backups/travis-$(date +%F).db'"` nightly, encrypted off-site copy, keep 30 days. Test a restore quarterly. Postgres: managed provider backups + point-in-time recovery.

## Runbook: common incidents

| Symptom | Likely cause | Fix |
|---|---|---|
| TRAVIS says "Let me make sure this gets to him directly" on every call | Core down or secret mismatch → every tool errors | `/health`; compare `VAPI_WEBHOOK_SECRET` with the platform's server secret/headers |
| Offers no times | Calendar auth expired, or rules too tight | Re-run `google_oauth.py`; check `booking_horizon_days`, `max_meetings_per_day` |
| Wrong "good morning/evening" | Static assistant (no `assistant-request`) | Use dynamic mode (`deploy_vapi.py --dynamic`) |
| Exec not receiving texts | 10DLC not approved, or carrier filtering | Twilio console → Messaging logs; finish registration |
| Transfers ring forever / loop | `executive.mobile` forwards back to TRAVIS | Use a direct number that doesn't forward |
| Exec texts get "passed your message along" | Number not in `command_numbers` (format) | Use E.164 `+1…` |
| Briefing sent twice | More than one worker running the scheduler | One worker, or `TRAVIS_SCHEDULER=false` + cron |

## Cost model (per executive)

Prices move; verify current rates. Rough 2026 ranges:

| Item | Unit cost | Typical exec (25 calls/day × 2.2 min × 30 days ≈ 1,650 min) |
|---|---|---|
| Voice platform orchestration | ~$0.05/min | ~$83 |
| STT + LLM (fast tier) + TTS | ~$0.05–0.12/min combined | ~$80–200 |
| Phone number | ~$1–2/mo | $2 |
| Telephony minutes (inbound + transfers) | ~$0.01–0.02/min | ~$25 |
| SMS (alerts, confirmations, briefing) | ~$0.008–0.012/segment + 10DLC fees | ~$10–20 |
| LLM for exec text channel | pennies per command | ~$5 |
| Hosting (Core + DB) | | ~$5–20 |
| **Total** | **~$0.12–0.22/min all-in** | **~$210–355/month** |

Levers: shorter calls (tight prompt, fast spam hang-ups), cheaper TTS voice, a smaller LLM on the voice loop, caching the prompt (many providers discount cached prefixes), and ending vendor calls in under 60 seconds.

## Pricing math at $797/month

- Gross margin at the typical exec above: roughly 55–75%.
- One-time setup ($797) covers ~6–8 hours of onboarding and QA.
- Heavy users (80+ calls/day, e.g. a CEO whose number is public) can cost $800+/month in minutes. Put a fair-use cap in the terms (e.g. 3,000 minutes/month included, then per-minute).
- The value comparison on the product page: virtual assistant $2,500+/mo, executive assistant $6,000+/mo, neither available nights, weekends or holidays.

## Change management

- Profile and knowledge edits: `POST /admin/reload` (admin token) picks them up without a restart.
- Prompt edits: re-run `build_voice_config.py`, `deploy_vapi.py`, then the regression checklist in `docs/10`.
- Keep a `CHANGELOG.md` per executive: what changed, why, who asked.
