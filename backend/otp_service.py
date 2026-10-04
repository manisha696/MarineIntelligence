import os
import base64
import importlib
from email.message import EmailMessage

from dotenv import load_dotenv


load_dotenv()

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")
GMAIL_SENDER = os.getenv("GMAIL_SENDER")


def generate_otp() -> str:
    import random
    return str(random.randint(100000, 999999))


def send_otp_email(recipient_email: str, otp: str):

    try:
        Credentials = importlib.import_module(
            "google.oauth2.credentials"
        ).Credentials
        build = importlib.import_module(
            "googleapiclient.discovery"
        ).build
    except ImportError as exc:
        raise RuntimeError(
            "Google API dependencies are not installed. Install "
            "google-auth and google-api-python-client."
        ) from exc

    if not GMAIL_CLIENT_ID:
        raise RuntimeError("GMAIL_CLIENT_ID is not configured")

    if not GMAIL_CLIENT_SECRET:
        raise RuntimeError("GMAIL_CLIENT_SECRET is not configured")

    if not GMAIL_REFRESH_TOKEN:
        raise RuntimeError("GMAIL_REFRESH_TOKEN is not configured")

    if not GMAIL_SENDER:
        raise RuntimeError("GMAIL_SENDER is not configured")

    credentials = Credentials(
        token=None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )

    service = build(
        "gmail",
        "v1",
        credentials=credentials
    )

    message = EmailMessage()

    message["From"] = GMAIL_SENDER
    message["To"] = recipient_email
    message["Subject"] = "Marine Intelligence - Email Verification OTP"

    message.set_content(
        f"""Marine Intelligence

Your email verification OTP is:

{otp}

This OTP is valid for 5 minutes.

If you did not request this verification, please ignore this email.

Regards,
Marine Intelligence Team
"""
    )

    encoded_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode()

    body = {
        "raw": encoded_message
    }

    service.users().messages().send(
        userId="me",
        body=body
    ).execute()