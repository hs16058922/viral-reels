#!/usr/bin/env python3
"""
Test Instagram authentication and session persistence.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    ChallengeRequired,
    PleaseWaitFewMinutes,
    TwoFactorRequired,
)

USERNAME = os.getenv("INSTAGRAM_USERNAME", "").strip()
PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "").strip()
SESSIONID = os.getenv("INSTAGRAM_SESSIONID", "").strip()
SESSION_FILE = PROJECT_ROOT / "tmp" / "ig_session.json"

cl = Client()
cl.delay_range = [2, 4]

# 1. Try sessionid cookie first if provided
if SESSIONID:
    print("Found INSTAGRAM_SESSIONID in .env! Connecting via session cookie...")
    try:
        cl.login_by_sessionid(SESSIONID)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(SESSION_FILE)
        print(f"  ✅ Connected successfully via sessionid! (User ID: {cl.user_id})")
    except Exception as e:
        print(f"  ❌ Sessionid login failed: {e}")

# 2. Try session file cache
elif SESSION_FILE.exists():
    try:
        print("  Found existing session cache. Attempting resume...")
        cl.load_settings(SESSION_FILE)
        cl.login(USERNAME, PASSWORD)
        print("  ✅ Session resumed successfully!")
    except Exception as e:
        print(f"  Session expired or invalid ({e}). Performing fresh login...")
        cl = Client()
        cl.delay_range = [2, 4]

if not cl.user_id:
    try:
        print("  Logging in with username & password...")
        cl.login(USERNAME, PASSWORD)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(SESSION_FILE)
        print(f"  ✅ Logged in successfully and saved session to {SESSION_FILE.name}!")
    except TwoFactorRequired:
        print("\n⚠️ TWO-FACTOR AUTHENTICATION REQUIRED")
        print("Instagram sent a security code to your phone or authenticator app.")
        code = input("Enter the 6-digit 2FA code: ").strip()
        cl.two_factor_login(code)
        cl.dump_settings(SESSION_FILE)
        print("  ✅ 2FA verified successfully!")
    except ChallengeRequired:
        print("\n⚠️ CHALLENGE REQUIRED")
        print("Instagram requires a security verification (email or SMS).")
        try:
            cl.challenge_resolve(cl.last_json)
            cl.dump_settings(SESSION_FILE)
            print("  ✅ Challenge resolved!")
        except Exception as ce:
            print(f"  ❌ Challenge error: {ce}")
            sys.exit(1)
    except BadPassword:
        print("  ❌ Error: Incorrect password.")
        sys.exit(1)
    except PleaseWaitFewMinutes:
        print("  ⚠️ Error: Instagram rate limit (Please wait a few minutes).")
        sys.exit(1)
    except Exception as exc:
        print(f"  ❌ Login failed: {exc}")
        sys.exit(1)

# Fetch profile details to verify full read/write capability
info = cl.user_info(cl.user_id)
print("\n" + "=" * 50)
print("🎉 Instagram Account Connected Successfully!")
print(f"  • Username: @{info.username}")
print(f"  • Full Name: {info.full_name or '(None)'}")
print(f"  • Followers: {info.follower_count}")
print(f"  • Media count: {info.media_count}")
print(f"  • Account type: {'Business/Creator' if info.is_business else 'Personal'}")
print("=" * 50)
