# 10 · Testing and QA

Three layers. Run all three before a new executive goes live and after any prompt, model, or rule change.

## Layer 1: unit tests (logic)

```bash
pytest server/tests -q
```

43 tests covering routing tiers and the decision matrix, urgency, calendar rules (protected blocks, buffers, notice, caps, weekends), the webhook protocol (argument formats, tool results, transfer destinations, end-of-call), booking/reschedule permissions, knowledge confidentiality, memory privacy, the briefing, the text channel, PIN enforcement and webhook secrets. CI runs them on every push (`.github/workflows/ci.yml`).

Add a test for every bug you fix. Most "TRAVIS did the wrong thing" reports turn out to be a routing or calendar rule, which is exactly what these tests pin down.

## Layer 2: simulations (tool flows)

```bash
python scripts/simulate_call.py all
python scripts/simulate_call.py all --url https://your-host   # against a deployment (set VAPI_WEBHOOK_SECRET)
```

Replays the scripted tool sequences for each call type with a frozen clock and the demo day. Use `--url` after a deploy as a smoke test: it proves the webhook, secret, database and calendar are wired. (Point it at a staging calendar, since it books and moves meetings.)

## Layer 3: live calls (conversation)

The model's behavior is only tested by talking to it.

1. Work through `evals/test-calls.md`: 30 scripted calls with pass criteria. Use real phones; caller ID matters.
2. Work through `evals/red-team.md`: social engineering and injection attempts. Must be 100%.
3. Score each call PASS/FAIL. Record the call ID and the reason for any failure.

### Automating layer 3

- Most platforms can run **test suites / simulated callers** (an AI caller following a script against your assistant). Put the eval scripts in as test cases and use the success-evaluation rubric from `prompts/end-of-call-analysis.md`.
- Or build a "caller bot" assistant on the same platform with a persona per scenario, and have it dial TRAVIS via an outbound call.
- Grade transcripts with an LLM using the rubric, but spot-check by hand; LLM graders are lenient on discretion failures.

## What to measure in production

| Metric | Target | Where |
|---|---|---|
| Answer rate | 100% | platform |
| First response latency | < 1.5 s p90 | platform call logs |
| Calls ending in < 15 s (non-spam) | < 5% | `calls` table, `ended_reason` |
| Calls with no outcome recorded | 0 | `calls.outcome IS NULL` |
| Transfer answer rate | > 80% | platform transfer events |
| Discretion failures | 0 | success evaluation + weekly transcript review |
| Messages marked handled within 24 h | > 90% | `messages` |
| Exec corrections by text ("no, don't book those") | trending down | exec thread |

## Regression checklist after changes

- Prompt edited → re-run test calls 1–10 and all red-team calls.
- Model or voice changed → all 30 + latency check.
- Routing/calendar rule changed → unit tests + simulations (+ the specific live call).
- New tool → add to `build_voice_config.py`, a unit test, a simulation scenario, and a live test call.
