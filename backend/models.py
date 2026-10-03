from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime

from database import Base


# ==================================================
# USER
# ==================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = Column(
        String,
        nullable=False
    )

    # Marine profile
    marine_profile = relationship(
        "MarineProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan"
    )


# ==================================================
# MARINE PROFILE
# ==================================================

class MarineProfile(Base):
    __tablename__ = "marine_profiles"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    user_type = Column(
        String,
        nullable=False
    )

    preferred_language = Column(
        String,
        default="English",
        nullable=False
    )

    latitude = Column(
        Float,
        nullable=True
    )

    longitude = Column(
        Float,
        nullable=True
    )

    boat_name = Column(
        String,
        nullable=True
    )

    boat_type = Column(
        String,
        nullable=True
    )

    user = relationship(
        "User",
        back_populates="marine_profile"
    )


# ==================================================
# OTP VERIFICATION
# ==================================================

class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    email = Column(
        String,
        nullable=False,
        index=True
    )

    otp = Column(
        String,
        nullable=False
    )

    purpose = Column(
        String,
        nullable=False,
        default="registration"
    )

    expires_at = Column(
        DateTime,
        nullable=False
    )

    verified = Column(
        Integer,
        default=0
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )