import os
import random
import smtplib

from email.message import EmailMessage
from dotenv import load_dotenv


# ==================================================
# LOAD ENVIRONMENT VARIABLES
# ==================================================

load_dotenv()


SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")


# ==================================================
# GENERATE OTP
# ==================================================

def generate_otp() -> str:
    return str(random.randint(100000, 999999))


# ==================================================
# SEND OTP EMAIL
# ==================================================

def send_otp_email(
    recipient_email: str,
    otp: str
):

    message = EmailMessage()

    message["Subject"] = "Marine Intelligence - Email Verification OTP"
    message["From"] = SMTP_FROM
    message["To"] = recipient_email

    message.set_content(
        f"""
Marine Intelligence

Your email verification OTP is:

{otp}

This OTP is valid for 5 minutes.

If you did not request this verification, please ignore this email.

Regards,
Marine Intelligence Team
"""
    )

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT
    ) as server:

        server.starttls()

        server.login(
            SMTP_USERNAME,
            SMTP_PASSWORD
        )

        server.send_message(message)