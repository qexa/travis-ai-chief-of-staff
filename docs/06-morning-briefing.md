# 06 · The Morning Protocol (daily briefing)

> "While you sleep, my task routing sorts the overnight calls, confirms your meetings and prepares a briefing on the matters that genuinely need you."

Implemented in `server/travis/briefing.py`. Sent at `briefing.send_at` (default 6:45 AM) by SMS and email.

## What's in it

```
Good morning, sir. Four meetings today, first at 8:30 AM.
I booked Alicia Moreno (Ridgeview Partners) intro for Tuesday 11:00.

▸ 3 calls handled overnight · 2 need your reply · 4 spam blocked

TODAY
  8:30 AM  Leadership staff meeting
  10 AM  Priya Nair (Crestline Freight) / Jordan: Q4 capacity
  1 PM  Board meeting
  3:30 PM  David Okafor / Jordan: renewal

NEEDS YOU
  ‼ Tom Becker, Becker & Stone LLP: Lease amendment needs your signature by Friday (+16155550302)
  Kevin Pratt, CloudStack: Vendor pitch: cloud cost software (+16155550500)

FOLLOW-UPS DUE
  • Sign Becker & Stone lease amendment

Reply with anything. "Move my 2pm to Friday", "Who called about the term sheet?"
```

| Section | Source | Rule |
|---|---|---|
| Headline | today's `meeting` events | count + first start time |
| What I did | `actions` since the last briefing | booked / moved / cancelled / blocked |
| Travel | today's `travel` events | time + title only |
| Stats line | `calls` since last briefing | spam counted separately |
| Today | calendar | chronological |
| Needs you | `messages` for exec not yet handled | critical/high first, flagged ‼ |
| Follow-ups due | `followups` owned by exec, due by tomorrow | |

"Since the last briefing" is tracked in `kv.last_briefing_at`; the first ever briefing looks back to 6 PM yesterday.

After sending, un-delivered messages are marked `delivered` (they stay in "Needs you" until the exec texts "done <name>" or they're marked handled).

## Design rules

1. **Readable in 20 seconds on a lock screen.** Headline first. Most important thing in the first 160 characters.
2. **Lead with what TRAVIS did, then what the exec must do.** That's the "chief of staff" feel.
3. **Never more than five items in a list.** Overflow goes to the email version.
4. **No spam details.** Just the count. It's proof of value, not information.
5. **Every briefing ends with an invitation to reply.** The text thread is the interface.

## Optional: LLM-polished briefing

The reference renders deterministically (no hallucination risk, zero cost). If you want a more conversational version, pass the output of `gather()` as JSON to an LLM with this prompt and send its result instead:

```
You are TRAVIS writing the executive's 6:45 AM briefing text. Use ONLY the JSON facts provided.
Open with "Good morning, {honorific}." then one sentence on the day's shape, one on what you handled,
then the items that need the executive, most urgent first. Plain text, under 700 characters,
no markdown. Never invent a meeting, caller, or number. If there's nothing urgent, say so.
```

Keep the deterministic version as the fallback if the LLM call fails.

## Evening reminders

`reminders.send_at` (default 6 PM): every external attendee with a phone number on tomorrow's meetings gets "Reminder: you're meeting with Mr. Hale tomorrow, 10 AM. Reply here if anything changes." Replies land in the exec's messages via `/sms/inbound`.
