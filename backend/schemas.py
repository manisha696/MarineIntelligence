from typing import Optional

from pydantic import BaseModel, EmailStr


# ==================================================
# AUTHENTICATION
# ==================================================

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ==================================================
# OTP VERIFICATION
# ==================================================

class OTPRequest(BaseModel):
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str


# ==================================================
# MARINE PROFILE
# ==================================================

class MarineProfileCreate(BaseModel):
    user_type: str
    preferred_language: str = "English"

    # SOS emergency contact
    family_contact_name: Optional[str] = None
    family_contact_number: Optional[str] = None
    relationship: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    boat_name: Optional[str] = None
    boat_type: Optional[str] = None

class MarineProfileResponse(BaseModel):
    id: int
    user_id: int

    user_type: str
    preferred_language: str

    # SOS emergency contact
    family_contact_name: Optional[str]
    family_contact_number: Optional[str]
    relationship: Optional[str]

    latitude: Optional[float]
    longitude: Optional[float]

    boat_name: Optional[str]
    boat_type: Optional[str]

    class Config:
        from_attributes = True

    class MarineProfileCreate(BaseModel):
     user_type: str
    preferred_language: str = "English"

    # SOS emergency contact
    family_contact_name: Optional[str] = None
    family_contact_number: Optional[str] = None
    relationship: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    boat_name: Optional[str] = None
    boat_type: Optional[str] = None    
