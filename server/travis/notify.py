"""Outbound SMS (Twilio) and email (SMTP). In demo mode both print and log to the outbox."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import httpx

from . import db
from .settings import get_settings

log = logging.getLogger("travis.notify")
SMS_LIMIT = 1500  # Twilio concatenates up to 1600 chars; stay under.


def send_sms(to: str, body: str) -> str:
    s = get_settings()
    body = body.strip()
    if len(body) > SMS_LIMIT:
        body = body[: SMS_LIMIT - 20].rstrip() + "\n…(full text by email)"
    if not s.sms_enabled:
        print(f"\n📱 [DEMO SMS → {to}]\n{body}\n")
        db.add_outbox("sms", to, body, "demo")
        return "demo"
    try:
        r = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
            data={"To": to, "From": s.twilio_from_number, "Body": body},
            auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=10,
        )
        r.raise_for_status()
        db.add_outbox("sms", to, body, "sent")
        return "sent"
    except Exception as exc:  # never let a notification failure break a live call
        log.exception("SMS failed")
        db.add_outbox("sms", to, body, "failed", error=str(exc))
        return "failed"


def send_email(to: str, subject: str, body: str, html: str | None = None) -> str:
    s = get_settings()
    if not s.email_enabled:
        print(f"\n✉️  [DEMO EMAIL → {to}] {subject}\n{body}\n")
        db.add_outbox("email", to, body, "demo", subject=subject)
        return "demo"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        db.add_outbox("email", to, body, "sent", subject=subject)
        return "sent"
    except Exception as exc:
        log.exception("Email failed")
        db.add_outbox("email", to, body, "failed", subject=subject, error=str(exc))
        return "failed"
