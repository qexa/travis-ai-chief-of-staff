import json


def call(client, name, args, caller="+16155550200", call_id="c1"):
    r = client.post("/vapi/webhook", json={"message": {
        "type": "tool-calls", "call": {"id": call_id, "customer": {"number": caller}},
        "toolCallList": [{"id": "tc1", "type": "function", "function": {"name": name, "arguments": args}}]}})
    assert r.status_code == 200
    body = r.json()["results"][0]
    assert body["toolCallId"] == "tc1"
    return json.loads(body["result"])


def test_health(client):
    assert client.get("/health").json()["ok"]


def test_lookup_and_route_vip(client, env):
    env["at"](13, 30)
    assert call(client, "lookup_caller", {})["tier"] == "vip"
    out = call(client, "route_call", {"reason": "term sheet", "urgency": "high"})
    assert out["action"] == "offer_callback"
    assert "+1615" not in json.dumps(out), "transfer numbers must never reach the model"


def test_arguments_as_json_string(client):
    r = client.post("/vapi/webhook", json={"message": {
        "type": "tool-calls", "call": {"id": "c9", "customer": {"number": "+16155550200"}},
        "toolCallList": [{"id": "x", "function": {"name": "lookup_caller", "arguments": "{\"name\": \"Cate\"}"}}]}})
    assert json.loads(r.json()["results"][0]["result"])["tier"] == "vip"


def test_book_flow_new_opportunity(client, env):
    caller = "+16155550444"
    call(client, "route_call", {"caller_name": "Marcus Lee", "reason": "Referred by David, want to explore working together",
                                "urgency": "normal"}, caller, "c2")
    slots = call(client, "check_availability", {"meeting_type": "standard"}, caller, "c2")
    assert slots["duration_minutes"] == 15, "new opportunities only get intro slots"
    res = call(client, "book_meeting", {"start": slots["slots"][0]["start"], "attendee_name": "Marcus Lee",
                                        "topic": "Intro"}, caller, "c2")
    assert res["booked"]
    # Same slot can't be double-booked
    again = call(client, "book_meeting", {"start": slots["slots"][0]["start"], "attendee_name": "X"}, caller, "c2")
    assert not again["booked"]


def test_vendor_cannot_book(client):
    caller = "+13125550777"
    call(client, "route_call", {"reason": "demo of our software platform", "urgency": "low"}, caller, "c3")
    assert call(client, "check_availability", {}, caller, "c3")["slots"] == []
    assert not call(client, "book_meeting", {"start": "2030-01-01T10:00:00", "attendee_name": "V"}, caller, "c3")["booked"]


def test_reschedule_only_own_meeting(client, env):
    env["at"](7, 30)
    priya, stranger = "+16155550301", "+16155550999"
    mine = call(client, "find_my_meeting", {}, priya, "c4")
    assert mine["found"]
    eid = mine["meetings"][0]["event_id"]
    slot = call(client, "check_availability", {}, priya, "c4")["slots"][0]["start"]
    denied = call(client, "reschedule_meeting", {"event_id": eid, "new_start": slot}, stranger, "c5")
    assert not denied["moved"]
    ok = call(client, "reschedule_meeting", {"event_id": eid, "new_start": slot}, priya, "c4")
    assert ok["moved"]


def test_transfer_destination_from_route(client, env):
    env["at"](13, 30)
    call(client, "route_call", {"caller_name": "Janet", "reason": "fire alarm and smoke on floor 4, emergency",
                                "urgency": "critical"}, "+16155550999", "c6")
    r = client.post("/vapi/webhook", json={"message": {"type": "transfer-destination-request",
                                                       "call": {"id": "c6", "customer": {"number": "+16155550999"}}}})
    assert r.json()["destination"]["number"] == env["profile"].exec["mobile"]


def test_no_transfer_for_vendor(client):
    call(client, "route_call", {"reason": "our software platform", "urgency": "low"}, "+13125550777", "c7")
    r = client.post("/vapi/webhook", json={"message": {"type": "transfer-destination-request",
                                                       "call": {"id": "c7", "customer": {"number": "+13125550777"}}}})
    assert "error" in r.json()


def test_take_message_and_end_of_call(client):
    from travis import db
    call(client, "take_message", {"caller_name": "Tom", "reason": "Lease", "details": "sign by Friday",
                                  "priority": "high"}, "+16155550302", "c8")
    client.post("/vapi/webhook", json={"message": {"type": "end-of-call-report", "endedReason": "customer-ended-call",
                                                   "call": {"id": "c8", "customer": {"number": "+16155550302"}},
                                                   "analysis": {"summary": "Tom needs a signature.",
                                                                "structuredData": {"action_items": [{"title": "Sign lease"}]}}}})
    row = db.one("SELECT * FROM calls WHERE call_id = 'c8'")
    assert row["outcome"] == "message" and row["summary"] == "Tom needs a signature."
    assert db.one("SELECT * FROM followups WHERE related_call_id = 'c8'")
    sms = db.query("SELECT * FROM outbox WHERE channel = 'sms'")
    assert any("HIGH message from Tom" in s["body"] for s in sms)


def test_text_caller_info_only_approved(client):
    assert call(client, "text_caller_info", {"info": "vendor_inbox"}, "+13125550777", "c9")["sent"]
    assert not call(client, "text_caller_info", {"info": "exec_cell"}, "+13125550777", "c9")["sent"]


def test_knowledge_hides_confidential(client):
    out = call(client, "search_knowledge", {"query": "acquisition pipeline target"}, "+13125550777", "c10")
    assert "CONFIDENTIAL" not in json.dumps(out)


def test_memory_not_given_to_impostor(client):
    out = call(client, "lookup_caller", {"name": "Catherine Blake"}, "+14155550111", "c11")
    assert out["things_to_remember"] == []


def test_tool_error_is_graceful(client):
    out = call(client, "book_meeting", {"start": "not-a-date", "attendee_name": "X"}, "+16155550200", "c12")
    assert out["booked"] is False


def test_webhook_secret_enforced(client, monkeypatch):
    from travis import settings
    monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "s3cret")
    settings.reset_settings()
    try:
        assert client.post("/vapi/webhook", json={"message": {"type": "status-update"}}).status_code == 401
        assert client.post("/vapi/webhook", json={"message": {"type": "status-update"}},
                           headers={"x-vapi-secret": "s3cret"}).status_code == 200
    finally:
        monkeypatch.setenv("VAPI_WEBHOOK_SECRET", "")
        settings.reset_settings()


def test_generic_tools_endpoint_retell_shape(client):
    r = client.post("/tools/lookup_caller", json={"call": {"call_id": "r1", "from_number": "+16155550200"}, "args": {}})
    assert r.json()["tier"] == "vip"
