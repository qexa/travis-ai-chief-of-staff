# 04 · Routing and priority

Implemented in `server/travis/routing.py`. Tested in `server/tests/test_routing.py`.

## Step 1: who is calling? (tier)

`classify_caller(phone, name, company, reason)` checks, in order:

1. **VIP list** in the profile, matched on **caller ID only** → `vip` or `inner_circle`, `verified=true`.
2. **Contacts table** (everyone who has called before) → their stored tier.
3. **Claimed VIP**: caller gives a VIP's name from an unknown number → treated as `known`, `claimed_vip=true`, `verified=false`. Never trusted on name alone (caller ID can be spoofed too, so VIP notes should never contain anything dangerous to say).
4. **Heuristics on the stated reason**:
   - spam signals ("extended warranty", "press one", "final notice") → `spam`
   - referral signals ("referred", "introduced", "recommended") → `new_opportunity` (checked **before** vendor words, so "referred by David, our software could help" is an opportunity)
   - vendor signals ("our platform", "five minutes", "SEO", "recruit") → `vendor`
   - opportunity signals ("interested in working", "quote", "investment") → `new_opportunity`
   - any other stated reason → `new_opportunity` (benefit of the doubt, but intro-only booking)
   - no reason yet → `unknown` → TRAVIS asks, then routes again

| Tier | Who | Transfer when free | Interrupt meetings | Book directly | Booking scope | SMS alert |
|---|---|---|---|---|---|---|
| `vip` | Board, investors, top clients | ✅ | only if critical | ✅ | extended hours | ✅ |
| `inner_circle` | Family | ✅ | ✅ except no-interrupt meetings | ❌ | n/a | ✅ |
| `known` | Existing contacts | ❌ (configurable) | ❌ | ✅ | standard | only if high |
| `new_opportunity` | Referrals, prospects | ❌ | ❌ | ✅ | 15-min intro only | ❌ |
| `vendor` | Pitches, recruiters | ❌ | ❌ | ❌ | n/a | ❌ |
| `spam` | Robocalls | ❌ | ❌ | ❌ | n/a | ❌ |

All of this is in the `tiers:` block of the profile; change it per executive.

## Step 2: how urgent? (priority)

`assess_urgency(reason, model_urgency)`:

- `critical_keywords` in the reason ("flood", "fire", "injured", "data breach", "lawsuit served") → **critical**, regardless of what the model said.
- `high_keywords` ("urgent", "term sheet", "wire", "deadline today") → at least **high**.
- Otherwise the model's own judgment stands (so "low" for a vendor stays low).

Keywords can only raise urgency, never lower it. The model can raise it too. This is deliberately asymmetric: a false "high" costs the exec a text; a missed "critical" costs much more.

## Step 3: the decision matrix

`decide()` evaluates top to bottom; the first match wins.

| # | Condition | Action |
|---|---|---|
| 1 | tier = spam | `end_spam` |
| 2 | urgency = critical and (`critical_from_anyone` or VIP/family) | `transfer_exec` + SMS alert; fallback message + backup (EA) |
| 2b | urgency = critical otherwise | `transfer_team` to `urgent_backup` |
| 3 | reason matches a team member's `handles` (not VIP/family) | business hours: `transfer_team`; after hours: message for that person + follow-up |
| 4 | tier = vendor | `screen_vendor` |
| 5 | tier = unknown | `screen` (ask name + reason) |
| 6 | VIP / family, exec available (or family after hours, or allowed to interrupt) | `transfer_exec` |
| 6b | VIP / family, exec busy | `offer_callback` with a concrete time (end of current meeting + 15 min) + SMS alert |
| 7 | known, claimed VIP | `take_message` (high), no schedule info |
| 7b | known | `offer_booking` or message |
| 8 | new opportunity | qualify, then `offer_booking` (intro) |

### Executive status

`executive_status()` reads the calendar *now*:

| State | Detected when | Caller hears |
|---|---|---|
| `in_meeting` | an event is in progress (back-to-back meetings are merged) | "He's in a meeting until 3" |
| `traveling` | the current event is `kind=travel` | "He's traveling right now" |
| `focus` | inside a protected block | "He's unavailable at the moment" |
| `after_hours` | outside `hours` | "He's out of the office for the day" |
| `available` | none of the above | "He's available" |

Plus an internal-only `no_interrupt` flag when the current meeting's title matches `calendar.no_interrupt_keywords`. The model never sees the meeting title.

## Transfers

- Warm vs cold: the reference uses a **cold transfer with an SMS heads-up** (the exec's phone shows the alert text as it rings). For a **warm transfer** (TRAVIS briefs the exec before connecting), use your platform's warm-transfer mode (Vapi supports warm transfer with a summary message) and return that mode from `transfer-destination-request`.
- Always configure a no-answer fallback on the platform: if the transfer isn't answered within ~20 s, return the caller to TRAVIS, who takes a message. The `if_no_answer` text from `route_call` tells the model what to say.
- Transfers loop if the exec's line forwards to TRAVIS. Use a direct number for `executive.mobile` (see build guide Phase 9).

## Tuning checklist

- Too many interruptions? Set VIP `can_interrupt_meetings: false`, narrow `high_keywords`, move people from `vip` to `known`.
- Missing important calls? Add them to `vips`; add industry terms to `high_keywords` ("LOI", "closing", "recall").
- Team drowning in transfers? Set `topic_routing.transfer_to_team_during_business_hours: false` (messages only).
- Every change: `pytest server/tests -q && python scripts/simulate_call.py all`.
