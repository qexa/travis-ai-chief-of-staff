# 05 · Calendar management

Implemented in `server/travis/calendar/`. Tested in `server/tests/test_calendar.py`.

## The rules TRAVIS enforces (in code, not in the prompt)

| Rule | Profile key | Example |
|---|---|---|
| Meeting hours | `earliest_meeting`, `latest_meeting_end` | 8:30 AM – 5:30 PM |
| VIP overflow window | `extended_earliest`, `extended_latest_end` | 7:30 AM – 6:30 PM for VIPs and the exec |
| Buffer before/after every meeting | `buffer_minutes` | 15 |
| Cap on meetings per day | `max_meetings_per_day` | 6 |
| Minimum notice | `min_notice_hours` | 2 hours |
| Booking horizon | `booking_horizon_days` | 14 days |
| Meeting-free days | `no_meeting_days` | `[fri]` |
| Protected blocks | `protected_blocks` | Tue/Thu 8:30–10:30 deep work; daily lunch |
| Meeting types | `meeting_types` | intro 15, standard 30, investor 45 |
| Who may book what | `tiers.*.booking_scope` | new opportunities: intro only |
| Caller reschedule / cancel | `caller_can_reschedule`, `caller_can_cancel` | yes / no |
| Never interrupt | `no_interrupt_keywords` | board meeting, keynote |

`is_slot_valid()` returns a caller-safe reason (`protected_time`, `conflict`, `day_full`, `too_soon`, …) that TRAVIS translates to "that time isn't available". The model never learns *why* (lunch, a doctor's appointment, a competitor meeting).

## Finding slots

`find_slots()` walks forward from today in `slot_step_minutes` increments and, by default, returns **one slot per day** for up to three days. People choose faster between "Tuesday at ten or Thursday at two" than between 2:00 and 2:15. `part_of_day` narrows to morning/afternoon/evening.

Double-booking protection: `book_meeting` re-validates the slot at booking time. If someone else took it in the last few seconds, TRAVIS gets `booked:false` and offers fresh times.

## What gets written to the calendar

- Title: `Marcus Lee (Summit Cold Chain) / Jordan: Intro: cold-chain partnership`
- Attendees with email get a native invite (`sendUpdates=all` on Google)
- Location: the exec's video link for video meeting types
- Description: "Booked by TRAVIS on a call. Tier, topic, call ID" so the exec can trace any booking to its transcript
- Caller gets an SMS confirmation immediately and a reminder the evening before (`reminders:`)
- Every change is written to the `actions` table and appears in the morning briefing ("I moved your 10:00 to 2:30")

## The executive's own changes (text channel)

"Move my 10am to Thursday" → `get_schedule` → `move_meeting(new_date)` → first valid standard-hours slot Thursday (extended hours only if the day is full). Explicit times ("to Friday at 7:30") are checked against the extended window; if they break a rule TRAVIS says which rule and asks before overriding (`force=true`). Cancellations need the PIN.

## Travel awareness

Events with `kind=travel` (Google: title contains "Flight", or extended property `travis_kind=travel`) make status "traveling". Callers hear only "traveling today". Tip: have the EA add flights to the calendar as their own events; TRAVIS will automatically stop offering slots during them.

## Calendar backends

| Backend | Status |
|---|---|
| `demo` (SQLite) | Complete; used by tests and simulations |
| `google` | Complete (REST + refresh token, no SDK) |
| Microsoft 365 | Implement the 5-method interface in `calendar/base.py` with Microsoft Graph: `GET /users/{id}/calendarView`, `POST /users/{id}/events`, `PATCH /users/{id}/events/{eventId}`, `DELETE …`. Use app-only auth with an application access policy limited to the exec's mailbox. |
| GoHighLevel / Votel.ai calendars | Either implement the interface against the platform's calendar API, or keep scheduling native to the platform and use Core only for routing/memory (`docs/13`). |

## Multiple calendars

Executives often have a personal calendar too. To block time without reading details, add the personal calendar's **free/busy** to `list_events` (Google `freeBusy` endpoint) and treat those blocks as `kind=personal` with title "(busy)". TRAVIS then avoids them and never knows what they are.
