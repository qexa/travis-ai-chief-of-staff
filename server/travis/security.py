"""Webhook authentication. Every inbound request must prove where it came from."""
from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi import HTTPException, Request

from .settings import get_settings


def verify_vapi(request: Request) -> None:
    """Vapi sends the assistant/server secret you configure as the `x-vapi-secret`
    header (or as a Bearer token when you use a Bearer credential). If no secret is
    configured we allow the request (demo mode) — never run like that in production."""
    secret = get_settings().vapi_webhook_secret
    if not secret:
        return
    header = request.headers.get("x-vapi-secret", "")
    auth = request.headers.get("authorization", "")
    bearer = auth[7:] if auth.lower().startswith("bearer ") else ""
    if hmac.compare_digest(header, secret) or (bearer and hmac.compare_digest(bearer, secret)):
        return
    raise HTTPException(status_code=401, detail="bad webhook secret")


def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    payload = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def verify_twilio(request: Request, params: dict[str, str]) -> None:
    s = get_settings()
    if not (s.twilio_auth_token and s.twilio_validate_signature):
        return
    # Use the public URL Twilio called (behind proxies request.url may differ).
    url = s.public_base_url.rstrip("/") + request.url.path
    expected = twilio_signature(s.twilio_auth_token, url, params)
    if not hmac.compare_digest(expected, request.headers.get("x-twilio-signature", "")):
        raise HTTPException(status_code=403, detail="bad twilio signature")


def verify_admin(request: Request) -> None:
    token = get_settings().admin_token
    if not token:
        return  # demo mode
    auth = request.headers.get("authorization", "")
    if not hmac.compare_digest(auth, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="admin token required")
