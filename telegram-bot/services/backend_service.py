"""
Wraps all calls from the Telegram bot to the backend REST API.
Every function here mirrors an endpoint in backend/routes/.
"""
import os
import requests

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:3000/api")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def login(email: str, password: str) -> dict:
    """Returns {token, user, workspace} or raises for invalid credentials."""
    resp = requests.post(f"{BACKEND_API_URL}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()


def signup(email: str, password: str, workspace_name: str, full_name: str = None) -> dict:
    """Returns {token, user, workspace, subscription} or raises (e.g. 409 if email taken)."""
    payload = {"email": email, "password": password, "workspaceName": workspace_name}
    if full_name:
        payload["fullName"] = full_name
    resp = requests.post(f"{BACKEND_API_URL}/auth/signup", json=payload)
    resp.raise_for_status()
    return resp.json()


def upload_media(token: str, file_path: str, mime_type: str) -> dict:
    """Uploads a downloaded Telegram file to the backend media library."""
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, mime_type)}
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(f"{BACKEND_API_URL}/media/upload", files=files, headers=headers)
    resp.raise_for_status()
    return resp.json()


def create_post(token: str, caption: str, platforms: list, media_ids: list, scheduled_time: str = None) -> dict:
    """scheduled_time as ISO string, or None to post immediately.
    Raises requests.HTTPError with response.status_code == 402 if the
    workspace's subscription isn't active yet (see get_billing_status)."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "caption": caption,
        "platforms": platforms,
        "mediaIds": media_ids,
    }
    if scheduled_time:
        payload["scheduledTime"] = scheduled_time

    resp = requests.post(f"{BACKEND_API_URL}/posts", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def list_connected_accounts(token: str) -> list:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_API_URL}/accounts", headers=headers)
    resp.raise_for_status()
    return resp.json().get("accounts", [])


def connect_account(token: str, platform: str, username: str, access_token: str = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"platform": platform, "username": username}
    if access_token:
        payload["accessToken"] = access_token
    resp = requests.post(f"{BACKEND_API_URL}/accounts", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_bot_share_link(token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_API_URL}/team/bot-link", headers=headers)
    resp.raise_for_status()
    return resp.json()


# ---------- Billing / subscription ----------

def get_billing_status(token: str) -> dict:
    """Returns {status, plan, trialEndsAt, currentPeriodEnd, pendingClaim}."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_API_URL}/billing/status", headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_pricing(token: str, cycle: str = None) -> dict:
    """No cycle -> {monthly: {...}, yearly: {...}}. With cycle -> a single quote dict:
    {cycle, currency, basePrice, discountPercent, finalPrice, promoName, periodDays}."""
    headers = {"Authorization": f"Bearer {token}"}
    params = {"cycle": cycle} if cycle else {}
    resp = requests.get(f"{BACKEND_API_URL}/billing/pricing", params=params, headers=headers)
    resp.raise_for_status()
    return resp.json()


def submit_claim(token: str, method: str, billing_cycle: str = "monthly", reference: str = None,
                  telegram_chat_id: str = None) -> dict:
    """method: 'local_manual' | 'crypto' | 'international'. billing_cycle: 'monthly' | 'yearly'.
    The price is computed server-side (including any live promo) - not sent from here."""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"method": method, "billingCycle": billing_cycle}
    if reference:
        payload["reference"] = reference
    if telegram_chat_id:
        payload["telegramChatId"] = telegram_chat_id
    resp = requests.post(f"{BACKEND_API_URL}/billing/claim", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def list_pending_claims() -> list:
    """Admin-only. Uses ADMIN_API_KEY, not a user token."""
    headers = {"x-admin-key": ADMIN_API_KEY}
    resp = requests.get(f"{BACKEND_API_URL}/billing/claims", params={"status": "pending"}, headers=headers)
    resp.raise_for_status()
    return resp.json().get("claims", [])


def approve_claim(claim_id: int) -> dict:
    """Admin-only. Returns {claim, subscription, telegramChatId}."""
    headers = {"x-admin-key": ADMIN_API_KEY}
    resp = requests.post(f"{BACKEND_API_URL}/billing/claims/{claim_id}/approve", headers=headers)
    resp.raise_for_status()
    return resp.json()


def reject_claim(claim_id: int) -> dict:
    """Admin-only. Returns {claim, telegramChatId}."""
    headers = {"x-admin-key": ADMIN_API_KEY}
    resp = requests.post(f"{BACKEND_API_URL}/billing/claims/{claim_id}/reject", headers=headers)
    resp.raise_for_status()
    return resp.json()


# ---------- Promotions (seasonal/marketing discounts) ----------

def set_promotion(name: str, discount_percent: int, billing_cycle: str = "both", days: int = None) -> dict:
    """Admin-only. Creates and activates a promo, replacing any currently-active one.
    billing_cycle: 'monthly' | 'yearly' | 'both'. days: how long it runs (omit = until /clearpromo)."""
    headers = {"x-admin-key": ADMIN_API_KEY}
    payload = {"name": name, "discountPercent": discount_percent, "billingCycle": billing_cycle}
    if days:
        payload["days"] = days
    resp = requests.post(f"{BACKEND_API_URL}/billing/promotions", json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()


def clear_promotion() -> dict:
    """Admin-only. Turns off any live promo."""
    headers = {"x-admin-key": ADMIN_API_KEY}
    resp = requests.post(f"{BACKEND_API_URL}/billing/promotions/clear", headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_active_promotion(token: str) -> dict:
    """Returns {monthly: {...}|None, yearly: {...}|None} - what's live right now."""
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_API_URL}/billing/promotions/active", headers=headers)
    resp.raise_for_status()
    return resp.json()
