"""Get a Gmail API refresh token for production email (run once, on your laptop).

    python3 scripts/gmail_refresh_token.py

It asks for the OAuth client ID and secret (Google Cloud → APIs & Services →
Credentials → OAuth client ID, type "Desktop app"), opens Google's sign-in page,
and prints the three values to paste into Render's Environment. Sign in with the
account that should send the emails. Nothing is written to disk.
"""

import getpass
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

SCOPE = "https://www.googleapis.com/auth/gmail.send"
PORT = 8765
REDIRECT_URI = f"http://127.0.0.1:{PORT}/"


def main():
    client_id = input("OAuth client ID: ").strip()
    client_secret = getpass.getpass("OAuth client secret (hidden): ").strip()
    state = secrets.token_urlsafe(16)

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        # offline + consent make Google return a refresh token every time.
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })

    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            query = parse_qs(urlparse(self.path).query)
            ok = query.get("state", [""])[0] == state and "code" in query
            result["code"] = query["code"][0] if ok else None
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"Done. You can close this tab and return to the terminal." if ok
                else b"Sign-in failed or was cancelled. Check the terminal."
            )

        def log_message(self, *args):
            pass

    print("\nOpening Google sign-in. If no browser opens, visit:\n" + auth_url + "\n")
    webbrowser.open(auth_url)
    HTTPServer(("127.0.0.1", PORT), Handler).handle_request()
    if not result.get("code"):
        raise SystemExit("No authorization code received.")

    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode({
            "code": result["code"],
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        tokens = json.loads(response.read())
    if "refresh_token" not in tokens:
        raise SystemExit("Google returned no refresh token. Remove the app's access at "
                         "myaccount.google.com/permissions and run this again.")

    print("Paste these into Render → your service → Environment:\n")
    print(f"GMAIL_CLIENT_ID={client_id}")
    print(f"GMAIL_CLIENT_SECRET={client_secret}")
    print(f"GMAIL_REFRESH_TOKEN={tokens['refresh_token']}")


if __name__ == "__main__":
    main()
