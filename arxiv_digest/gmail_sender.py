"""Send multipart plain-text and HTML digests through the Gmail API."""

from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
TOKEN_URI = "https://oauth2.googleapis.com/token"
ENVIRONMENT_CREDENTIALS = (
    "GMAIL_CLIENT_ID",
    "GMAIL_CLIENT_SECRET",
    "GMAIL_REFRESH_TOKEN",
)


class GmailDeliveryError(RuntimeError):
    """Raised when Gmail credentials are invalid or delivery fails."""


def build_email_message(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
) -> EmailMessage:
    """Build the RFC-compatible MIME message submitted to Gmail."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    return message


def _load_credentials(token_file: Path) -> Any:
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise GmailDeliveryError(
            "Google client libraries are not installed; run "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    present = {name: os.environ.get(name) for name in ENVIRONMENT_CREDENTIALS}
    if any(present.values()):
        missing = [name for name, value in present.items() if not value]
        if missing:
            raise GmailDeliveryError(
                "Incomplete Gmail environment credentials; missing: "
                + ", ".join(missing)
            )
        return Credentials(
            token=None,
            refresh_token=present["GMAIL_REFRESH_TOKEN"],
            token_uri=TOKEN_URI,
            client_id=present["GMAIL_CLIENT_ID"],
            client_secret=present["GMAIL_CLIENT_SECRET"],
            scopes=[GMAIL_SEND_SCOPE],
        )

    if token_file.is_file():
        try:
            return Credentials.from_authorized_user_file(
                str(token_file), [GMAIL_SEND_SCOPE]
            )
        except (OSError, ValueError) as exc:
            raise GmailDeliveryError(
                f"Could not load Gmail token file {token_file}: {exc}"
            ) from exc

    raise GmailDeliveryError(
        "No Gmail credentials found. Run 'python -m arxiv_digest.gmail_auth' "
        f"to create {token_file}, or set {', '.join(ENVIRONMENT_CREDENTIALS)}."
    )


def send_email_via_gmail(
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    token_file: Path = Path("token.json"),
) -> str:
    """Send one message and return the Gmail message ID."""
    try:
        from google.auth.exceptions import GoogleAuthError
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as exc:
        raise GmailDeliveryError(
            "Google client libraries are not installed; run "
            "'python -m pip install -r requirements.txt'."
        ) from exc

    credentials = _load_credentials(token_file)
    message = build_email_message(sender, recipient, subject, body, html_body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    try:
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": encoded})
            .execute()
        )
    except (GoogleAuthError, HttpError, OSError, ValueError) as exc:
        raise GmailDeliveryError(f"Gmail API delivery failed: {exc}") from exc

    message_id = result.get("id")
    if not message_id:
        raise GmailDeliveryError("Gmail API response did not include a message ID.")
    return str(message_id)
