"""Loads the executive profile YAML and exposes small typed helpers."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from .settings import get_settings

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def normalize_phone(raw: str | None) -> str:
    """Return E.164-ish digits with a leading +. US 10-digit numbers get +1."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits if digits else ""


def parse_hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


@dataclass
class Profile:
    data: dict[str, Any]

    # ── convenience accessors ──────────────────────────────────────────────
    @property
    def exec(self) -> dict[str, Any]:
        return self.data["executive"]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.exec.get("timezone", "America/Chicago"))

    @property
    def team(self) -> list[dict[str, Any]]:
        return self.data.get("team", [])

    @property
    def tiers(self) -> dict[str, dict[str, Any]]:
        return self.data.get("tiers", {})

    @property
    def calendar(self) -> dict[str, Any]:
        return self.data.get("calendar", {})

    @property
    def urgency(self) -> dict[str, Any]:
        return self.data.get("urgency", {})

    def now(self) -> datetime:
        # TRAVIS_FAKE_NOW (ISO datetime) freezes the clock for demos, simulations and tests.
        fake = os.environ.get("TRAVIS_FAKE_NOW")
        if fake:
            dt = datetime.fromisoformat(fake)
            return dt.replace(tzinfo=self.tz) if dt.tzinfo is None else dt.astimezone(self.tz)
        return datetime.now(self.tz)

    def team_member(self, key: str) -> dict[str, Any] | None:
        return next((t for t in self.team if t.get("key") == key), None)

    def vip_by_phone(self, phone: str) -> dict[str, Any] | None:
        target = normalize_phone(phone)
        if not target:
            return None
        for vip in self.data.get("vips", []):
            if normalize_phone(vip.get("phone")) == target:
                return vip
        return None

    def vip_by_name(self, name: str) -> dict[str, Any] | None:
        if not name:
            return None
        n = name.strip().lower()
        for vip in self.data.get("vips", []):
            full = vip["name"].lower()
            first = full.split()[0]
            if n == full or (len(n.split()) == 1 and n == first):
                return vip
        return None

    def is_command_number(self, phone: str) -> bool:
        allowed = {normalize_phone(p) for p in self.exec.get("command_numbers", [])}
        return normalize_phone(phone) in allowed

    def is_business_hours(self, when: datetime | None = None) -> bool:
        when = (when or self.now()).astimezone(self.tz)
        hours = self.data.get("hours", {})
        if DAY_KEYS[when.weekday()] not in hours.get("business_days", DAY_KEYS[:5]):
            return False
        return parse_hhmm(hours.get("start", "08:00")) <= when.time() < parse_hhmm(hours.get("end", "18:00"))

    def part_of_day(self, when: datetime | None = None) -> str:
        h = (when or self.now()).astimezone(self.tz).hour
        if h < 12:
            return "morning"
        if h < 17:
            return "afternoon"
        return "evening"

    def pronoun_forms(self) -> dict[str, str]:
        p = self.exec.get("pronoun", "they")
        return {
            "he": {"subj": "he", "obj": "him", "poss": "his", "be": "he's"},
            "she": {"subj": "she", "obj": "her", "poss": "her", "be": "she's"},
        }.get(p, {"subj": "they", "obj": "them", "poss": "their", "be": "they're"})


@lru_cache(maxsize=4)
def _load(path: str) -> Profile:
    with Path(path).open() as fh:
        return Profile(yaml.safe_load(fh))


def get_profile() -> Profile:
    return _load(get_settings().profile_path)


def reload_profile() -> Profile:
    _load.cache_clear()
    return get_profile()
