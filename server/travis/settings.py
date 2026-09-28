"""Runtime settings, read from environment variables (and an optional .env file).

Everything has a safe default so the server runs in DEMO MODE with zero keys:
- calendar = local SQLite demo calendar
- SMS / email = printed to the console and stored in the outbox table
- LLM = rule-based fallback for the executive command channel
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no dependency). Existing env vars win."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(REPO_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    # Core
    profile_path: str = field(default_factory=lambda: _env("TRAVIS_PROFILE", str(REPO_ROOT / "config" / "executive.example.yaml")))
    db_path: str = field(default_factory=lambda: _env("TRAVIS_DB", str(REPO_ROOT / "travis.db")))
    knowledge_dir: str = field(default_factory=lambda: _env("TRAVIS_KNOWLEDGE_DIR", str(REPO_ROOT / "knowledge" / "example")))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL", "http://localhost:8000"))
    admin_token: str = field(default_factory=lambda: _env("TRAVIS_ADMIN_TOKEN"))

    # Voice platform (Vapi reference)
    vapi_api_key: str = field(default_factory=lambda: _env("VAPI_API_KEY"))
    vapi_webhook_secret: str = field(default_factory=lambda: _env("VAPI_WEBHOOK_SECRET"))
    vapi_assistant_id: str = field(default_factory=lambda: _env("VAPI_ASSISTANT_ID"))

    # Calendar
    calendar_backend: str = field(default_factory=lambda: _env("CALENDAR_BACKEND", "demo"))  # demo | google
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    google_refresh_token: str = field(default_factory=lambda: _env("GOOGLE_REFRESH_TOKEN"))
    google_calendar_id: str = field(default_factory=lambda: _env("GOOGLE_CALENDAR_ID", "primary"))

    # SMS (Twilio)
    twilio_account_sid: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    twilio_from_number: str = field(default_factory=lambda: _env("TWILIO_FROM_NUMBER"))
    twilio_validate_signature: bool = field(default_factory=lambda: _env("TWILIO_VALIDATE_SIGNATURE", "true").lower() == "true")

    # Email (SMTP)
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    email_from: str = field(default_factory=lambda: _env("EMAIL_FROM", "travis@example.com"))

    # LLM (executive command channel + briefing polish)
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("TRAVIS_LLM_MODEL", "claude-sonnet-5"))

    @property
    def sms_enabled(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Used by tests after changing environment variables."""
    global _settings
    _settings = None
