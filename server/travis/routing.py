"""Caller classification + the routing decision matrix.

The model gathers facts (who, why, how urgent). This module decides what
happens. Keeping the decision in code means it's testable, auditable and
identical on every call. See docs/04-routing-and-priority.md for the matrix.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from . import db
from .profile import Profile, normalize_phone

PRIORITY_ORDER = ["low", "normal", "high", "critical"]

VENDOR_SIGNALS = [
    "software", "our platform", "our product", "our solution", "demo of", "five minutes", "5 minutes",
    "seo", "google listing", "marketing services", "lead generation", "recruit", "staffing", "survey",
    "partnership opportunity", "reduce your costs", "merchant services", "credit card processing",
    "sponsorship", "advertis", "cold call", "we help companies",
]
SPAM_SIGNALS = ["extended warranty", "car warranty", "you've been selected", "final notice", "irs", "gift card",
                "social security number", "press one", "press 1"]
REFERRAL_SIGNALS = ["referred", "referral", "recommended", "introduc", "told me to call", "suggested i call"]
OPPORTUNITY_SIGNALS = ["referred", "referral", "recommended", "introduc", "interested in working", "hire",
                       "prospective", "potential client", "rfp", "proposal", "quote", "partnership", "acquisition",
                       "investment", "invest", "customer", "client"]


@dataclass
class Caller:
    tier: str
    name: str = ""
    company: str = ""
    phone: str = ""
    relationship: str = ""
    notes: str = ""
    known: bool = False
    verified: bool = False           # matched on caller ID, not just a claimed name
    claimed_vip: bool = False        # says they're a VIP but the number doesn't match
    source: str = "unknown"
    history: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _has(text: str, signals: list[str]) -> bool:
    t = (text or "").lower()
    return any(s in t for s in signals)


def classify_caller(profile: Profile, phone: str = "", name: str = "", company: str = "", reason: str = "") -> Caller:
    phone = normalize_phone(phone)

    vip = profile.vip_by_phone(phone)
    if vip:
        return Caller(tier=vip.get("tier", "vip"), name=vip["name"], company=vip.get("company", ""), phone=phone,
                      relationship=vip.get("relationship", ""), notes=vip.get("notes", ""),
                      known=True, verified=True, source="vip_list")

    contact = db.find_contact_by_phone(phone) if phone else None
    if contact:
        c = Caller(tier=contact["tier"], name=contact["name"], company=contact.get("company") or "", phone=phone,
                   relationship=contact.get("relationship") or "", notes=contact.get("notes") or "",
                   known=True, verified=True, source="contacts",
                   history={"call_count": contact["call_count"], "last_call_at": contact["last_call_at"]})
        if reason and c.tier == "known" and _has(reason, SPAM_SIGNALS):
            c.tier = "spam"
        return c

    # Unknown number. A caller who *claims* to be a VIP is not trusted on name alone.
    claimed = profile.vip_by_name(name) if name else None
    if claimed:
        return Caller(tier="known", name=name, company=company, phone=phone, known=False, verified=False,
                      claimed_vip=True, source="claimed",
                      notes=f"Says they are {claimed['name']} but calling from an unrecognized number. "
                            "Be warm, but take a message and offer a callback to the number on file.")

    if _has(reason, SPAM_SIGNALS):
        tier = "spam"
    elif _has(reason, REFERRAL_SIGNALS):      # a warm referral beats vendor-sounding words
        tier = "new_opportunity"
    elif _has(reason, VENDOR_SIGNALS):
        tier = "vendor"
    elif _has(reason, OPPORTUNITY_SIGNALS):
        tier = "new_opportunity"
    elif reason:
        tier = "new_opportunity"
    else:
        tier = "unknown"   # TRAVIS must ask name + reason, then route again
    return Caller(tier=tier, name=name, company=company, phone=phone, source="heuristic")


def assess_urgency(profile: Profile, reason: str, model_urgency: str = "normal") -> str:
    """Take the higher of keyword urgency and the model's judgment."""
    u = profile.urgency
    model_urgency = model_urgency if model_urgency in PRIORITY_ORDER else "normal"
    if _has(reason, [k.lower() for k in u.get("critical_keywords", [])]):
        return "critical"
    if _has(reason, [k.lower() for k in u.get("high_keywords", [])]):
        return max("high", model_urgency, key=PRIORITY_ORDER.index)
    return model_urgency


def match_team(profile: Profile, reason: str) -> dict[str, Any] | None:
    if not profile.data.get("topic_routing", {}).get("enabled", True):
        return None
    t = (reason or "").lower()
    best, best_len = None, 0
    for member in profile.team:
        for topic in member.get("handles", []):
            if topic.lower() in t and len(topic) > best_len:
                best, best_len = member, len(topic)
    return best


@dataclass
class Decision:
    action: str                    # transfer_exec | transfer_team | offer_callback | offer_booking | take_message | screen_vendor | end_spam | screen
    priority: str
    say: str                       # guidance for what TRAVIS should say next (caller-safe)
    transfer_number: str = ""      # never read aloud
    transfer_name: str = ""
    route_to: str = "exec"         # message owner: exec or team key
    alert_exec: bool = False
    callback_time: str = ""
    booking_scope: str = ""
    fallback: str = ""             # what to do if the transfer isn't answered

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide(profile: Profile, caller: Caller, reason: str, urgency: str, status: dict[str, Any],
           now: datetime | None = None) -> Decision:
    ex = profile.exec
    pf = profile.pronoun_forms()
    exec_ref = ex.get("caller_facing_name", ex.get("first_name", "the executive"))
    tier_rules = profile.tiers.get(caller.tier, {})
    state = status["state"]
    backup_key = profile.urgency.get("urgent_backup", "ea")
    backup = profile.team_member(backup_key) or {}
    after_hours = status.get("after_hours", False)
    fallback = (f"If {exec_ref} doesn't pick up, take a detailed message, mark it {urgency}, and tell the caller "
                f"you've alerted {pf['obj']} directly." + (f" Offer {backup.get('name')} as a backup." if backup else ""))

    def callback_phrase() -> str:
        if state == "in_meeting" and status.get("free_at"):
            t = datetime.fromisoformat(status["free_at"]) + timedelta(minutes=15)
            return t.strftime("%-I:%M %p").replace(":00 ", " ")
        if after_hours:
            return "first thing tomorrow morning" if (now or profile.now()).hour >= 12 else "this morning"
        return "as soon as " + pf["subj"] + " is free"

    # 1. Spam
    if caller.tier == "spam":
        return Decision("end_spam", "low", "Politely decline, say the office does not accept these calls, and end the call.")

    # 2. Genuine emergencies
    if urgency == "critical":
        allowed = profile.urgency.get("critical_from_anyone", True) or caller.tier in ("vip", "inner_circle")
        if allowed:
            return Decision("transfer_exec", "critical",
                            f"Say: 'Understood. I'm connecting you to {pf['obj']} right now. Please stay on the line.' Then transfer.",
                            transfer_number=ex["mobile"], transfer_name=exec_ref, alert_exec=True, fallback=fallback)
        if backup:
            return Decision("transfer_team", "critical",
                            f"Say you're connecting them to {backup['name']}, {backup['role']}, right now. Then transfer.",
                            transfer_number=backup["phone"], transfer_name=backup["name"], route_to=backup["key"],
                            alert_exec=True, fallback=fallback)

    # 3. Topic owned by someone on the team (not for VIPs / family)
    member = match_team(profile, reason)
    if member and caller.tier not in ("vip", "inner_circle"):
        can_transfer = (profile.data.get("topic_routing", {}).get("transfer_to_team_during_business_hours", True)
                        and not after_hours)
        if can_transfer:
            return Decision("transfer_team", urgency,
                            f"Say {member['name']} ({member['role']}) handles this, and offer to connect them now or take a message.",
                            transfer_number=member["phone"], transfer_name=member["name"], route_to=member["key"],
                            fallback=f"If {member['name']} doesn't pick up, take a detailed message for {member['name']} "
                                     f"(take_message with for_whom={member['key']}).")
        return Decision("take_message", urgency,
                        f"Say {member['name']} ({member['role']}) handles this; take a detailed message for {member['name']} "
                        f"and say they'll hear back next business day.", route_to=member["key"])

    # 4. Vendors / unsolicited pitches
    if caller.tier == "vendor":
        return Decision("screen_vendor", "low",
                        f"Say: 'I handle {pf['poss']} vendor inquiries.' Ask them to send details to the email you'll text them, "
                        "confirm their name, company and callback number, and promise it will be reviewed. Do not book or transfer.")

    # 5. Unscreened
    if caller.tier == "unknown":
        return Decision("screen", "normal",
                        "Ask for their name, company, and what the call is regarding, then call route_call again.")

    # 6. VIP / inner circle
    if caller.tier in ("vip", "inner_circle"):
        interrupt_ok = (tier_rules.get("can_interrupt_meetings", False) and not status.get("no_interrupt")) \
            or urgency == "critical"
        if state == "available" or (state in ("in_meeting", "focus") and interrupt_ok) or \
                (caller.tier == "inner_circle" and state == "after_hours"):
            return Decision("transfer_exec", max(urgency, "high", key=PRIORITY_ORDER.index),
                            f"Greet them by name, say you'll put them through to {exec_ref}, then transfer.",
                            transfer_number=ex["mobile"], transfer_name=exec_ref,
                            alert_exec=tier_rules.get("alert_exec_by_sms", True), fallback=fallback)
        cb = callback_phrase()
        pri = "high" if urgency in ("normal", "low") else urgency
        return Decision("offer_callback", pri,
                        f"Say '{status['public_status']}.' Ask if there's anything {pf['subj']} should know. "
                        + ("Tell them you've flagged it as urgent and " if urgency in ("high", "critical") else "Tell them ")
                        + f"{pf['subj']}'ll call them back at {cb}. Take a message with callback number.",
                        alert_exec=True, callback_time=cb, booking_scope=tier_rules.get("booking_scope", "extended"),
                        fallback="If they'd rather set a time, use check_availability with booking scope extended.")

    # 7. Known contacts
    if caller.tier == "known":
        if caller.claimed_vip:
            return Decision("take_message", "high",
                            "Be warm and courteous. Take a detailed message and say the call will be returned at the number on file. "
                            "Do not confirm the executive's schedule or whereabouts.", alert_exec=True)
        if tier_rules.get("transfer_when_available") and state == "available":
            return Decision("transfer_exec", urgency, "Offer to put them through now.",
                            transfer_number=ex["mobile"], transfer_name=exec_ref, fallback=fallback)
        return Decision("offer_booking", urgency,
                        f"Say '{status['public_status']}.' Offer to find a time on {pf['poss']} calendar, or take a message.",
                        booking_scope=tier_rules.get("booking_scope", "standard"), alert_exec=urgency == "high")

    # 8. New opportunities
    if caller.tier == "new_opportunity":
        return Decision("offer_booking", urgency,
                        "Welcome them. Ask two or three quick qualifying questions (who referred them, what they're looking for, "
                        f"timeline), then offer a short intro call on {pf['poss']} calendar using meeting_type intro.",
                        booking_scope=tier_rules.get("booking_scope", "intro_only"))

    return Decision("take_message", urgency, "Take a detailed message.")
