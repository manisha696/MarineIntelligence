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
# MARINE PROFILE
# ==================================================

class MarineProfileCreate(BaseModel):
    user_type: str
    preferred_language: str = "English"

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    boat_name: Optional[str] = None
    boat_type: Optional[str] = None


class MarineProfileResponse(BaseModel):
    id: int
    user_id: int

    user_type: str
    preferred_language: str

    latitude: Optional[float]
    longitude: Optional[float]

    boat_name: Optional[str]
    boat_type: Optional[str]

    class Config:
        from_attributes = True