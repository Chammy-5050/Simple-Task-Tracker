import base64
import json
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Access tokens last about an hour; reuse one across emails instead of
# refreshing for every message.
_token = {"value": "", "expires_at": 0.0}
_token_lock = threading.Lock()


def _post(url, data, headers):
    request = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read() or b"{}")
    except HTTPError as error:
        # Report Google's error code without echoing credentials.
        try:
            reason = json.loads(error.read()).get("error")
        except ValueError:
            reason = None
        if isinstance(reason, dict):
            reason = reason.get("status") or reason.get("message")
        raise RuntimeError(f"Gmail API request failed: HTTP {error.code} ({reason}).") from error


def _access_token():
    with _token_lock:
        if _token["value"] and time.time() < _token["expires_at"] - 60:
            return _token["value"]
        for name in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN"):
            if not getattr(settings, name, ""):
                raise ValueError(f"{name} is missing.")
        data = _post(
            TOKEN_URL,
            urlencode({
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "refresh_token": settings.GMAIL_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            }).encode(),
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        _token["value"] = data["access_token"]
        _token["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        return _token["value"]


class GmailApiEmailBackend(BaseEmailBackend):
    """Send through the Gmail API over HTTPS (works where SMTP ports are blocked).

    Emails go out from the Google account that granted the refresh token, so
    DEFAULT_FROM_EMAIL should be that account's address.
    """

    def send_messages(self, email_messages):
        sent = 0

        for message in email_messages:
            if not message.recipients():
                continue

            try:
                # Django builds the full MIME message (text, HTML, attachments).
                raw = base64.urlsafe_b64encode(message.message().as_bytes()).decode()
                _post(
                    SEND_URL,
                    json.dumps({"raw": raw}).encode(),
                    {
                        "Authorization": f"Bearer {_access_token()}",
                        "Content-Type": "application/json",
                    },
                )
                sent += 1

            except Exception:
                if not self.fail_silently:
                    raise

        return sent
