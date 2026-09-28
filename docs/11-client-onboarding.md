# 11 · Client onboarding ("trained on your business")

How to take a new executive from signed to live in about a week, with one 60-minute interview. This is the process behind the one-time setup on the product page.

## Timeline

| Day | What | Who |
|---|---|---|
| 0 | Kickoff email + intake form + calendar access request | You |
| 1 | 60-minute discovery interview (exec + EA) | You, exec, EA |
| 1–2 | Build profile, knowledge base, VIP list; configure number | You |
| 2 | Internal QA: unit tests, simulations, 30 test calls | You |
| 3 | "Hear TRAVIS before you hire him" demo call with the exec, on their own scenarios | You, exec |
| 3–4 | Adjustments; EA review of VIP list and rules | You, EA |
| 5 | Go live: forwarding on, first briefing next morning | You |
| 5–19 | Hypercare: daily transcript review, weekly tune-up | You |

## Intake form (send before the interview)

**Executive**
- Full name, title, company; how TRAVIS should address you (sir / ma'am / first name) and how he should refer to you to callers
- Time zone; mobile for transfers (a direct line that does NOT forward to TRAVIS); email
- Working hours; days you never take meetings

**People**
- Top 10–20 people who should always be recognized: name, company, relationship, mobile number(s), how to handle them
- Family members who should be put through
- Your EA / chief of staff / team: who handles what (billing, press, travel, IT, facilities, legal)
- Anyone who should never be put through

**Calendar**
- Earliest/latest meetings; buffer between meetings; max meetings per day
- Blocks to protect (deep work, lunch, workouts, school pickup, family dinner)
- Meeting types and lengths; default video link
- Meetings that must never be interrupted (board, keynotes, depositions)
- Can callers reschedule their own meetings? Cancel?

**Urgency**
- What counts as an emergency for you? Words or situations that should always reach you
- Who's the backup when you can't be reached?

**Company**
- Website, one-page overview, services, locations, hours, FAQ, press contact, careers page, vendor policy
- Anything confidential TRAVIS must never discuss

**Briefing**
- What time? SMS, email, or both? Weekends?

## Discovery interview agenda (60 min)

1. (5) What a great day looks like; what currently falls through the cracks
2. (15) Walk through last week's calls and calendar: who called, what should have happened
3. (15) VIPs and the team: go name by name
4. (10) Calendar rules and sacred time
5. (10) Urgency, escalation, discretion ("what should TRAVIS never say?")
6. (5) Voice and persona: play 2–3 voice samples; pick one

## Build checklist

- [ ] `config/<slug>.yaml` from the intake
- [ ] `knowledge/<slug>/` from the website + interview (templates in `knowledge/templates/`)
- [ ] Calendar OAuth completed by the exec or EA (screen-share if needed)
- [ ] Number purchased or forwarding plan agreed; direct transfer number confirmed
- [ ] Command number(s) and PIN set; exec tested a text command
- [ ] `pytest`, `simulate_call.py all`, 30 test calls, red-team 18/18

## Client-facing one-pager ("How TRAVIS works for you")

> **TRAVIS answers every call to your office, 24/7.**
>
> **Gets through to you immediately:** [VIP names], your family, and true emergencies.
> **Gets a callback time:** VIPs when you're busy. You get a text right away.
> **Gets a meeting:** clients and referred prospects, on your calendar's open time only. Never over [protected blocks].
> **Goes to your team:** billing → [name], press → [name], building → [name].
> **Gets screened:** sales pitches and recruiters. You see them in the briefing; they don't reach your phone.
> **Gets blocked:** spam and robocalls.
>
> **Every morning at [6:45]:** your day, what I handled overnight, and who needs you.
> **Any time:** text me. "Move my 2pm to Friday." "Who called about the lease?" "Remember that…"
>
> **I never:** give out your number or whereabouts, discuss your meetings, make commitments for you, or pretend to be human.

## Pricing reference (as shown on travis.autoanswer.app)

$797/month, one-time setup of $797 covering training on the business, people and preferences; no long-term contract. Positioned against a virtual assistant ($2,500+/mo) and an executive assistant ($6,000+/mo) who don't work nights, weekends or holidays. Your own pricing math is in `docs/12`.
