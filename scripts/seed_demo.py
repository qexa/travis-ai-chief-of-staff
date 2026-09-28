#!/usr/bin/env python3
"""Load the fictional executive's day (calendar, overnight calls, messages) into the local DB.

    python scripts/seed_demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from travis.demo_data import seed  # noqa: E402

if __name__ == "__main__":
    ids = seed()
    print("Seeded demo data for Jordan Hale:")
    for k, v in ids.items():
        print(f"  {k:10} {v}")
