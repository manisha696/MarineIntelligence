import os
import requests

from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_URL = "https://api.resend.com/emails"

# Use the sender address available in your Resend account.
# For initial testing, Resend may provide an onboarding sender.
RESEND_FROM = os.getenv(
    "RESEND_FROM",
    "Marine Intelligence <onboarding@resend.dev>"
)


def generate_otp() -> str:
    import random

    return str(random.randint(100000, 999999))


def send_otp_email(recipient_email: str, otp: str):
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY is not configured")

    payload = {
        "from": RESEND_FROM,
        "to": [recipient_email],
        "subject": "Marine Intelligence - Email Verification OTP",
        "text": f"""
Marine Intelligence

Your email verification OTP is:

{otp}

This OTP is valid for 5 minutes.

If you did not request this verification, please ignore this email.

Regards,
Marine Intelligence Team
"""
    }

    response = requests.post(
        RESEND_URL,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=20
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Resend API error {response.status_code}: {response.text}"
        )