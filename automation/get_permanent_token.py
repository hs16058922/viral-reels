"""
Exchange short-lived token for a PERMANENT, NEVER-EXPIRING Page Access Token.

Meta Graph API Rule:
When you exchange a short-lived user token for a long-lived user token (60 days),
and THEN query /me/accounts, the returned Page Access Token NEVER EXPIRES.
"""

import sys
import requests


def get_permanent_page_token(app_id: str, app_secret: str, short_lived_user_token: str):
    print("=" * 60)
    print("🔑 GENERATING PERMANENT (NEVER-EXPIRING) PAGE ACCESS TOKEN")
    print("=" * 60)

    # 1. Exchange short-lived token for 60-day long-lived User Token
    exchange_url = "https://graph.facebook.com/v19.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id.strip(),
        "client_secret": app_secret.strip(),
        "fb_exchange_token": short_lived_user_token.strip(),
    }

    print("\n[1/3] Exchanging short-lived token for 60-day user token...")
    resp = requests.get(exchange_url, params=params)
    data = resp.json()

    if "access_token" not in data:
        print("❌ Error exchanging token:", data)
        return

    long_lived_user_token = data["access_token"]
    print("  ✅ Long-lived user token generated successfully!")

    # 2. Query /me/accounts using the long-lived user token
    print("\n[2/3] Fetching Permanent Page Access Token from /me/accounts...")
    accounts_url = "https://graph.facebook.com/v19.0/me/accounts"
    acc_params = {
        "access_token": long_lived_user_token,
        "fields": "id,name,access_token,instagram_business_account",
    }

    acc_resp = requests.get(accounts_url, params=acc_params)
    acc_data = acc_resp.json()

    pages = acc_data.get("data", [])
    if not pages:
        print("❌ No pages found:", acc_data)
        return

    # 3. Find Curiomotion or first connected page
    print(f"  Found {len(pages)} page(s):")
    selected_page = None
    for p in pages:
        ig_acc = p.get("instagram_business_account", {}).get("id")
        print(f"  - Page: '{p.get('name')}' (ID: {p.get('id')}) | Instagram ID: {ig_acc}")
        if ig_acc:
            selected_page = p

    if not selected_page:
        selected_page = pages[0]

    perm_token = selected_page["access_token"]
    ig_id = selected_page.get("instagram_business_account", {}).get("id", "")

    # 4. Verify token expiration via debug_token
    print("\n[3/3] Verifying token expiration...")
    debug_url = f"https://graph.facebook.com/v19.0/debug_token?input_token={perm_token}&access_token={perm_token}"
    dbg_resp = requests.get(debug_url)
    dbg_data = dbg_resp.json().get("data", {})
    expires_at = dbg_data.get("expires_at", 0)

    print("\n" + "=" * 60)
    print("🎉 SUCCESS! HERE ARE YOUR PERMANENT CREDENTIALS:")
    print("=" * 60)
    if expires_at == 0:
        print("⏰ Token Expiration: NEVER EXPIRES (0) ✅")
    else:
        print(f"⏰ Token Expiration: {expires_at}")
    print(f"📌 INSTAGRAM_ACCOUNT_ID={ig_id}")
    print(f"🔑 INSTAGRAM_ACCESS_TOKEN={perm_token}")
    print("=" * 60)
    print("\nUpdate your GitHub Secrets and local .env with this new INSTAGRAM_ACCESS_TOKEN!")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python automation/get_permanent_token.py <APP_ID> <APP_SECRET> <SHORT_LIVED_TOKEN>")
        sys.exit(1)
    get_permanent_page_token(sys.argv[1], sys.argv[2], sys.argv[3])
