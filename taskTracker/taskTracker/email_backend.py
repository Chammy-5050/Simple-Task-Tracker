import json
from email.utils import parseaddr
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


def address(value):
    name, email = parseaddr(value)
    result = {"email": email}
    if name:
        result["name"] = name
    return result


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0

        for message in email_messages:
            if not message.recipients():
                continue

            try:
                if not settings.BREVO_API_KEY:
                    raise ValueError("BREVO_API_KEY is missing.")

                # This backend supports text/HTML emails, not attachments.
                if message.attachments:
                    raise ValueError("Attachments are not supported.")

                payload = {
                    "sender": address(message.from_email),
                    "subject": message.subject,
                }

                for field in ("to", "cc", "bcc"):
                    recipients = getattr(message, field)
                    if recipients:
                        payload[field] = [
                            address(value) for value in recipients
                        ]

                if message.reply_to:
                    payload["replyTo"] = address(message.reply_to[0])

                html = next(
                    (
                        content
                        for content, mimetype in getattr(
                            message, "alternatives", []
                        )
                        if mimetype == "text/html"
                    ),
                    None,
                )

                if html is not None:
                    payload["htmlContent"] = html
                elif message.content_subtype == "html":
                    payload["htmlContent"] = message.body
                else:
                    payload["textContent"] = message.body

                request = Request(
                    "https://api.brevo.com/v3/smtp/email",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "api-key": settings.BREVO_API_KEY,
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    method="POST",
                )

                try:
                    with urlopen(request, timeout=15) as response:
                        if response.status != 201:
                            raise RuntimeError(
                                f"Unexpected Brevo status: {response.status}"
                            )
                except HTTPError as error:
                    # Report the status without exposing credentials.
                    raise RuntimeError(
                        f"Brevo rejected the email: HTTP {error.code}. "
                        "Check your API permissions and verified sender."
                    ) from error

                sent += 1

            except Exception:
                if not self.fail_silently:
                    raise

        return sent