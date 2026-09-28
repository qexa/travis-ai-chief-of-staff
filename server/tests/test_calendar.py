from datetime import datetime, time, timedelta

from travis.calendar.availability import find_slots, is_slot_valid


def dt(env, d, h, m=0):
    return datetime.combine(env["monday"] + timedelta(days=d), time(h, m), env["profile"].tz)


def test_protected_lunch_never_offered(env):
    ok, why = is_slot_valid(env["profile"], dt(env, 1, 12, 15), 30)
    assert not ok and why == "protected_time"


def test_deep_work_block_on_tuesday(env):
    ok, why = is_slot_valid(env["profile"], dt(env, 1, 9), 30)
    assert not ok and why == "protected_time"


def test_buffer_around_existing_meetings(env):
    # Board meeting 13:00-15:00 Monday; 15:05 violates the 15-minute buffer.
    ok, why = is_slot_valid(env["profile"], dt(env, 0, 15, 5), 15)
    assert not ok and why == "conflict"


def test_min_notice(env):
    env["at"](9, 30)
    ok, why = is_slot_valid(env["profile"], dt(env, 0, 10, 45), 15)
    assert not ok and why == "too_soon"


def test_outside_hours_standard_but_ok_extended(env):
    p = env["profile"]
    assert is_slot_valid(p, dt(env, 2, 7, 45), 30)[1] == "outside_meeting_hours"
    assert is_slot_valid(p, dt(env, 2, 7, 45), 30, scope="extended")[0]


def test_weekend_never_offered(env):
    slots = find_slots(env["profile"], 30, earliest=env["monday"] + timedelta(days=5),
                       latest=env["monday"] + timedelta(days=6))
    assert slots == []


def test_find_slots_spreads_across_days_and_all_valid(env):
    p = env["profile"]
    slots = find_slots(p, 30, limit=3)
    assert len(slots) == 3
    assert len({s.start.date() for s in slots}) == 3
    for s in slots:
        assert is_slot_valid(p, s.start, 30)[0]


def test_max_meetings_per_day(env):
    from travis.calendar import get_calendar
    p = env["profile"]
    cal = get_calendar()
    for h in (9, 10, 11, 14, 15, 16):
        cal.create_event(f"m{h}", dt(env, 3, h), dt(env, 3, h, 30), [])
    ok, why = is_slot_valid(p, dt(env, 3, 13, 15), 15)
    assert not ok and why == "day_full"
