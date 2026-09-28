from travis.briefing import run_briefing
from travis.commands import handle_exec_message


def sms(client, frm, body):
    return client.post("/sms/inbound", data={"From": frm, "Body": body}).text


def test_briefing_contents(env):
    env["at"](6, 45)
    text = run_briefing(send=False)
    assert text.startswith("Good morning, sir. Four meetings today")
    assert "4 spam blocked" in text
    assert "Tom Becker" in text and "‼" in text
    assert "Sign Becker & Stone lease amendment" in text


def test_briefing_send_marks_delivered(env):
    from travis import db
    env["at"](6, 45)
    run_briefing(send=True)
    assert db.kv_get("last_briefing_at")
    assert not db.query("SELECT * FROM messages WHERE status = 'new'")
    assert db.query("SELECT * FROM outbox WHERE channel = 'email'")


def test_move_meeting_by_text(env):
    env["at"](7, 0)
    reply = handle_exec_message("move my 10am to thursday")
    assert reply.startswith("Done.") and "Thu" in reply


def test_remember_and_recall(env):
    handle_exec_message("remember that the Okafor renewal target is 3 years")
    assert "3 years" in handle_exec_message("what do you know about okafor")


def test_only_exec_number_can_command(client, env):
    assert "Leadership staff meeting" in sms(client, "+16155550100", "schedule")
    stranger = sms(client, "+16155550777", "schedule")
    assert "passed your message along" in stranger
    from travis import db
    assert db.one("SELECT * FROM messages WHERE from_phone = '+16155550777'")


def test_cancel_requires_pin(env):
    from travis.exec_tools import cancel_meeting
    from travis.tools import CallContext
    eid = env["ids"]["priya"]
    assert not cancel_meeting({"event_id": eid, "pin": "0000"}, CallContext())["cancelled"]
    assert cancel_meeting({"event_id": eid, "pin": "4417"}, CallContext())["cancelled"]
