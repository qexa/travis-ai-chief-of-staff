from datetime import timedelta

from travis.calendar.availability import executive_status
from travis.routing import assess_urgency, classify_caller, decide


def _route(env, phone="", name="", reason="", urgency="normal"):
    p = env["profile"]
    c = classify_caller(p, phone, name, "", reason)
    u = assess_urgency(p, reason, urgency)
    return c, decide(p, c, reason, u, executive_status(p))


def test_vip_recognized_by_caller_id(env):
    c = classify_caller(env["profile"], "(615) 555-0200")
    assert c.tier == "vip" and c.verified and c.name == "Catherine Blake"


def test_vip_in_board_meeting_gets_callback_not_transfer(env):
    env["at"](13, 30)
    c, d = _route(env, "+16155550200", reason="Thursday's term sheet", urgency="high")
    assert d.action == "offer_callback"
    assert d.callback_time == "3:15 PM"
    assert d.alert_exec


def test_vip_when_free_is_transferred(env):
    env["at"](11, 15)
    _, d = _route(env, "+16155550200", reason="Quick catch-up")
    assert d.action == "transfer_exec" and d.transfer_number == env["profile"].exec["mobile"]


def test_family_not_put_through_during_board_meeting(env):
    env["at"](13, 45)
    _, d = _route(env, "+16155550202", reason="Personal call")
    assert d.action == "offer_callback"


def test_family_put_through_otherwise(env):
    env["at"](16, 30)
    _, d = _route(env, "+16155550202", reason="Personal call")
    assert d.action == "transfer_exec"


def test_critical_from_unknown_caller_is_transferred(env):
    env["at"](13, 30)
    c, d = _route(env, "+16155559999", "Janet", "There's a flood in the building")
    assert c.tier == "new_opportunity"
    assert d.action == "transfer_exec" and d.priority == "critical"


def test_impostor_claiming_vip_name_is_not_trusted(env):
    c, d = _route(env, "+14155550111", "Catherine Blake", "Where is Jordan?")
    assert c.claimed_vip and not c.verified
    assert d.action == "take_message"


def test_vendor_screened(env):
    c, d = _route(env, "+13125550777", "Brad", "I'd love five minutes to show you our software platform")
    assert c.tier == "vendor" and d.action == "screen_vendor"


def test_referral_beats_vendor_words(env):
    c, d = _route(env, "+13125550778", "Marcus", "Referred by David, our software could help your cold-chain")
    assert c.tier == "new_opportunity" and d.action == "offer_booking"


def test_spam_ended(env):
    c, d = _route(env, "+18885550999", reason="anything")
    assert c.tier == "spam" and d.action == "end_spam"


def test_topic_routes_to_team_in_business_hours(env):
    env["at"](10, 15)
    _, d = _route(env, "+16155550666", "Dana", "Unpaid invoice from August")
    assert d.action == "transfer_team" and d.transfer_name == "Marcus Reed"


def test_topic_after_hours_becomes_message_for_team(env):
    env["at"](19, 0)
    _, d = _route(env, "+16155550666", "Dana", "Unpaid invoice from August")
    assert d.action == "take_message" and d.route_to == "cfo_office"


def test_urgency_keywords_raise_but_never_lower(env):
    p = env["profile"]
    assert assess_urgency(p, "the term sheet", "normal") == "high"
    assert assess_urgency(p, "hello", "critical") == "critical"
    assert assess_urgency(p, "vendor pitch", "low") == "low"


def test_status_never_leaks_meeting_title(env):
    env["at"](13, 30)
    s = executive_status(env["profile"])
    assert "Board" not in s["public_status"] and "until 3 PM" in s["public_status"]
