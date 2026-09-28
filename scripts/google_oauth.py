#!/usr/bin/env python3
"""Get a Google Calendar refresh token for the executive's account (one time).

1. Google Cloud Console → APIs & Services → enable "Google Calendar API".
2. Credentials → Create OAuth client ID → type "Desktop app". Copy the id and secret.
3. OAuth consent screen: add the exec's Google account as a test user (or publish the app).
4. Run:  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... python scripts/google_oauth.py
5. Open the printed URL, sign in AS THE EXECUTIVE (or the delegated EA account), approve,
   and paste the `code` from the redirected URL back here.
6. Put the printed refresh token in GOOGLE_REFRESH_TOKEN and set CALENDAR_BACKEND=google.
"""
import os
import sys
import urllib.parse

import httpx

SCOPE = "https://www.googleapis.com/auth/calendar"
REDIRECT = "http://localhost:8765/"

cid, secret = os.environ.get("GOOGLE_CLIENT_ID"), os.environ.get("GOOGLE_CLIENT_SECRET")
if not (cid and secret):
    sys.exit("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET first.")

url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
    "access_type": "offline", "prompt": "consent"})
print("\nOpen this URL, approve, then copy the `code=` value from the address bar\n"
      "(the page itself will fail to load; that's expected):\n\n" + url + "\n")
code = input("code: ").strip()
code = urllib.parse.unquote(code.split("code=")[-1].split("&")[0])
r = httpx.post("https://oauth2.googleapis.com/token", data={
    "code": code, "client_id": cid, "client_secret": secret, "redirect_uri": REDIRECT, "grant_type": "authorization_code"})
r.raise_for_status()
tok = r.json().get("refresh_token")
print("\nGOOGLE_REFRESH_TOKEN=" + (tok or "(none returned: revoke access at myaccount.google.com/permissions and retry)"))
