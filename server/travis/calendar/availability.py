"""Calendar protection + slot finding + "where is the exec right now".

This is the part that makes TRAVIS a chief of staff and not a booking link:
every rule in the profile's `calendar:` block is enforced here, in code, so
the model can never talk its way past a protected block.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..profile import DAY_KEYS, Profile, parse_hhmm
from . import Event, get_calendar


@dataclass
class Slot:
    start: datetime
    end: datetime

    def spoken(self, tz) -> str:
        s = self.start.astimezone(tz)
        return s.strftime("%A, %B %-d at %-I:%M %p").replace(":00 ", " ")

    def as_dict(self, tz) -> dict:
        return {"start": self.start.astimezone(tz).isoformat(), "end": self.end.astimezone(tz).isoformat(),
                "spoken": self.spoken(tz)}


def _window_for_day(profile: Profile, day: date, scope: str) -> tuple[datetime, datetime] | None:
    cal = profile.calendar
    if DAY_KEYS[day.weekday()] in cal.get("no_meeting_days", []):
        return None
    if DAY_KEYS[day.weekday()] not in profile.data.get("hours", {}).get("business_days", DAY_KEYS[:5]):
        return None
    if scope == "extended":
        start_t = parse_hhmm(cal.get("extended_earliest", cal.get("earliest_meeting", "08:30")))
        end_t = parse_hhmm(cal.get("extended_latest_end", cal.get("latest_meeting_end", "17:30")))
    else:
        start_t = parse_hhmm(cal.get("earliest_meeting", "08:30"))
        end_t = parse_hhmm(cal.get("latest_meeting_end", "17:30"))
    tz = profile.tz
    return datetime.combine(day, start_t, tz), datetime.combine(day, end_t, tz)


def _protected_for_day(profile: Profile, day: date) -> list[tuple[datetime, datetime, str]]:
    out = []
    for block in profile.calendar.get("protected_blocks", []):
        if DAY_KEYS[day.weekday()] in block.get("days", []):
            out.append((datetime.combine(day, parse_hhmm(block["start"]), profile.tz),
                         datetime.combine(day, parse_hhmm(block["end"]), profile.tz), block.get("label", "Protected")))
    return out


def _overlaps(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def is_slot_valid(profile: Profile, start: datetime, minutes: int, scope: str = "standard",
                  events: list[Event] | None = None, ignore_event_id: str | None = None,
                  now: datetime | None = None) -> tuple[bool, str]:
    """Return (ok, reason). Reason is caller-safe (never reveals what's on the calendar)."""
    cal = profile.calendar
    tz = profile.tz
    start = start.astimezone(tz)
    end = start + timedelta(minutes=minutes)
    now = (now or profile.now()).astimezone(tz)
    if start < now + timedelta(hours=cal.get("min_notice_hours", 2)):
        return False, "too_soon"
    if start.date() > (now + timedelta(days=cal.get("booking_horizon_days", 14))).date():
        return False, "too_far_out"
    window = _window_for_day(profile, start.date(), scope)
    if not window or start < window[0] or end > window[1]:
        return False, "outside_meeting_hours"
    for p0, p1, _label in _protected_for_day(profile, start.date()):
        if _overlaps(start, end, p0, p1):
            return False, "protected_time"
    buf = timedelta(minutes=cal.get("buffer_minutes", 0))
    day_start = datetime.combine(start.date(), time(0), tz)
    if events is None:
        events = get_calendar().list_events(day_start, day_start + timedelta(days=1))
    same_day = [e for e in events if e.id != ignore_event_id and e.start.astimezone(tz).date() == start.date()]
    for e in same_day:
        if _overlaps(start - buf, end + buf, e.start, e.end):
            return False, "conflict"
    meetings = [e for e in same_day if e.kind == "meeting"]
    if len(meetings) >= cal.get("max_meetings_per_day", 99):
        return False, "day_full"
    return True, "ok"


def find_slots(profile: Profile, minutes: int, scope: str = "standard", earliest: date | None = None,
               latest: date | None = None, part_of_day: str = "any", limit: int = 3,
               now: datetime | None = None, spread_days: bool = True, ignore_event_id: str | None = None) -> list[Slot]:
    """Find up to `limit` valid slots. With spread_days, offers at most one slot per day
    (callers decide faster between "Tuesday or Thursday" than between 2:00 and 2:15)."""
    cal = profile.calendar
    tz = profile.tz
    now = (now or profile.now()).astimezone(tz)
    earliest = max(earliest or now.date(), now.date())
    horizon = now.date() + timedelta(days=cal.get("booking_horizon_days", 14))
    latest = min(latest or horizon, horizon)
    step = timedelta(minutes=cal.get("slot_step_minutes", 15))

    range_start = datetime.combine(earliest, time(0), tz)
    range_end = datetime.combine(latest + timedelta(days=1), time(0), tz)
    events = get_calendar().list_events(range_start, range_end)

    slots: list[Slot] = []
    day = earliest
    while day <= latest and len(slots) < limit:
        window = _window_for_day(profile, day, scope)
        if window:
            cursor = window[0]
            while cursor + timedelta(minutes=minutes) <= window[1]:
                if part_of_day == "morning" and cursor.hour >= 12:
                    break
                if part_of_day == "afternoon" and not (12 <= cursor.hour < 17):
                    cursor += step
                    continue
                if part_of_day == "evening" and cursor.hour < 16:
                    cursor += step
                    continue
                ok, _ = is_slot_valid(profile, cursor, minutes, scope, events, ignore_event_id, now)
                if ok:
                    slots.append(Slot(cursor, cursor + timedelta(minutes=minutes)))
                    if spread_days or len(slots) >= limit:
                        break
                    cursor += timedelta(minutes=minutes)  # next non-overlapping option
                    continue
                cursor += step
        day += timedelta(days=1)
    return slots[:limit]


def executive_status(profile: Profile, now: datetime | None = None) -> dict:
    """What TRAVIS may say about the exec right now + the private detail for internal logic."""
    tz = profile.tz
    now = (now or profile.now()).astimezone(tz)
    pf = profile.pronoun_forms()
    day_start = datetime.combine(now.date(), time(0), tz)
    events = get_calendar().list_events(day_start, day_start + timedelta(days=2))
    current = next((e for e in events if e.start <= now < e.end), None)
    protected_now = next((p for p in _protected_for_day(profile, now.date()) if p[0] <= now < p[1]), None)
    traveling_today = any(e.kind == "travel" and e.start.astimezone(tz).date() == now.date() for e in events)
    after_hours = not profile.is_business_hours(now)

    # When does the current busy stretch end? Walk back-to-back meetings.
    free_at = None
    if current:
        free_at = current.end
        changed = True
        while changed:
            changed = False
            for e in events:
                if e.start <= free_at < e.end or (timedelta(0) <= e.start - free_at <= timedelta(minutes=5)):
                    if e.end > free_at:
                        free_at, changed = e.end, True

    if current and current.kind == "travel":
        state, public = "traveling", f"{pf['be'].capitalize()} traveling right now"
    elif current:
        until = free_at.astimezone(tz).strftime("%-I:%M %p").replace(":00 ", " ")
        state, public = "in_meeting", f"{pf['be'].capitalize()} in a meeting until {until}"
    elif protected_now:
        state, public = "focus", f"{pf['be'].capitalize()} unavailable at the moment"
    elif after_hours:
        state, public = "after_hours", f"{pf['be'].capitalize()} out of the office for the day"
    else:
        state, public = "available", f"{pf['be'].capitalize()} available"
    if traveling_today and state not in ("traveling",):
        public += ", and traveling today"

    no_int_words = [w.lower() for w in profile.calendar.get("no_interrupt_keywords", [])]
    no_interrupt = bool(current and any(w in current.title.lower() for w in no_int_words))

    return {
        "state": state,
        "no_interrupt": no_interrupt,       # internal only: never sent to the model
        "public_status": public,
        "free_at": free_at.astimezone(tz).isoformat() if free_at else None,
        "free_at_spoken": free_at.astimezone(tz).strftime("%-I:%M %p").replace(":00 ", " ") if free_at else None,
        "traveling_today": traveling_today,
        "after_hours": after_hours,
        "now": now.isoformat(),
    }
