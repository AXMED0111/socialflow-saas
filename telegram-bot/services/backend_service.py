"""
Wraps all calls from the Telegram bot to the backend REST API.
Every function here mirrors an endpoint in backend/routes/.
"""
import os
import requests

BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:3000/api")


def login(email: str, password: str) -> dict:
    """Returns {token, user, workspace} or raises for invalid credentials."""
    resp = requests.post(f"{BACKEND_API_URL}/auth/login", json={"email": email, "password": password})
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
    """scheduled_time as ISO string, or None to post immediately."""
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


def get_bot_share_link(token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(f"{BACKEND_API_URL}/team/bot-link", headers=headers)
    resp.raise_for_status()
    return resp.json()
