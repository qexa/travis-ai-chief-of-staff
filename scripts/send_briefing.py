#!/usr/bin/env python3
"""Build the morning briefing.

    python scripts/send_briefing.py --print          # print only (seeds demo data if the DB is empty)
    python scripts/send_briefing.py --send           # send via SMS/email as configured

For production, either leave TRAVIS_SCHEDULER=true (in-process timer) or call
POST /briefing/run?send=true from cron / your platform's scheduler.
"""
import argparse
import os
import sys
from datetime import datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from travis import db  # noqa: E402
from travis.briefing import run_briefing  # noqa: E402
from travis.profile import get_profile  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--print", action="store_true", default=True)
    g.add_argument("--send", action="store_true")
    a = ap.parse_args()
    if not db.query("SELECT id FROM events LIMIT 1"):
        from travis.demo_data import seed
        seed()
        print("(Database was empty: seeded demo data.)\n")
    p = get_profile()
    if a.print and not a.send:
        from travis.demo_data import _next_weekday
        os.environ.setdefault("TRAVIS_FAKE_NOW", datetime.combine(_next_weekday(p.now().date()), time(6, 45)).isoformat())
    print(run_briefing(send=a.send))
