import os
from importlib import import_module
from datetime import datetime, timedelta

from dotenv import load_dotenv
from satellite import router as satellite_router
from sst import router as sst_router
from pfz import router as pfz_router
from risk import router as risk_router
try:
    pfz_router = import_module("pfz").router
except ModuleNotFoundError as exc:
    if exc.name != "pfz":
        raise
    pfz_router = None

from fastapi import (
    FastAPI,
    Depends,
    HTTPException
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from sqlalchemy.orm import Session

import bcrypt

from jose import jwt, JWTError

from database import (
    engine,
    Base,
    get_db
)

from models import (
    User,
    MarineProfile,
    OTPVerification
)

from schemas import (
    RegisterRequest,
    LoginRequest,
    OTPRequest,
    OTPVerifyRequest,
    MarineProfileCreate,
    MarineProfileResponse
)
from otp_service import (
    generate_otp,
    send_otp_email
)


# ==================================================
# ENVIRONMENT
# ==================================================

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")

ALGORITHM = "HS256"


# ==================================================
# DATABASE
# ==================================================

Base.metadata.create_all(
    bind=engine
)


# ==================================================
# FASTAPI
# ==================================================

app = FastAPI(
    title="Marine Intelligence API",
    version="0.1.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(satellite_router)
app.include_router(sst_router)
app.include_router(pfz_router)
app.include_router(risk_router)

if pfz_router is not None:
    app.include_router(pfz_router)
# ==================================================
# PASSWORD HASHING
# ==================================================

# ==================================================
# PASSWORD HASHING
# ==================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )


# ==================================================
# JWT SECURITY
# ==================================================

security = HTTPBearer(
    scheme_name="BearerAuth",
    description="Enter your JWT access token"
)


# ==================================================
# ROOT
# ==================================================

@app.get("/")
def root():

    return {
        "message": "Marine Intelligence API Running"
    }
# ==================================================
# REQUEST REGISTRATION OTP
# ==================================================

@app.post("/register/request-otp")
def request_registration_otp(
    otp_request: OTPRequest,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == otp_request.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    new_otp = OTPVerification(
        email=otp_request.email,
        otp=otp,
        purpose="registration",
        expires_at=expires_at,
        verified=0
    )

    db.add(new_otp)
    db.commit()

    try:
        send_otp_email(
            otp_request.email,
            otp
        )

    except Exception as e:
        print("OTP EMAIL ERROR:", repr(e))

        db.delete(new_otp)
        db.commit()

        raise HTTPException(
            status_code=500,
            detail="Unable to send OTP email"
        )

    return {
        "message": "OTP sent successfully",
        "email": otp_request.email
    }
# ==================================================
# REGISTER
# ==================================================
# ==================================================
# REGISTER
# ==================================================
@app.post("/register/verify-otp")
def verify_registration_otp(
    otp_request: OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    otp_record = db.query(
        OTPVerification
    ).filter(
        OTPVerification.email == otp_request.email,
        OTPVerification.purpose == "registration",
        OTPVerification.verified == 0
    ).order_by(
        OTPVerification.created_at.desc()
    ).first()

    if not otp_record:
        raise HTTPException(
            status_code=400,
            detail="OTP not found or already verified"
        )

    if datetime.utcnow() > otp_record.expires_at:
        raise HTTPException(
            status_code=400,
            detail="OTP has expired"
        )

    if otp_record.otp != otp_request.otp:
        raise HTTPException(
            status_code=400,
            detail="Invalid OTP"
        )

    otp_record.verified = 1
    db.commit()

    return {
        "message": "Email verified successfully",
        "email": otp_request.email
    }

@app.post("/register")
def register(
    user_data: RegisterRequest,
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    verified_otp = db.query(
        OTPVerification
    ).filter(
        OTPVerification.email == user_data.email,
        OTPVerification.purpose == "registration",
        OTPVerification.verified == 1
    ).order_by(
        OTPVerification.created_at.desc()
    ).first()

    if not verified_otp:
        raise HTTPException(
            status_code=400,
            detail="Please verify your email with OTP before registration"
        )

    hashed_password = hash_password(
        user_data.password
    )

    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed_password
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    token_data = {
    "sub": str(new_user.id),
    "email": new_user.email,
    "exp": datetime.utcnow()
    + timedelta(hours=24)
    }

    access_token = jwt.encode(
    token_data,
    SECRET_KEY,
    algorithm=ALGORITHM
    )

    return {
    "message": "User registered successfully",
    "user_id": new_user.id,
    "name": new_user.name,
    "email": new_user.email,
    "access_token": access_token,
    "token_type": "bearer"
    }

# ==================================================
# LOGIN
# ==================================================

@app.post("/login")
def login(
    user_data: LoginRequest,
    db: Session = Depends(get_db)
):

    user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if not user:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    password_correct = verify_password(
    user_data.password,
    user.password_hash
    )

    if not password_correct:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.utcnow()
        + timedelta(hours=24)
    }

    access_token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email
        }
    }


# ==================================================
# AUTHENTICATED USER HELPER
# ==================================================

def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    ),
    db: Session = Depends(get_db)
):

    token = credentials.credentials

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:

            raise HTTPException(
                status_code=401,
                detail="Invalid token"
            )

    except JWTError:

        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    user = db.query(User).filter(
        User.id == int(user_id)
    ).first()

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user


# ==================================================
# GET CURRENT USER
# ==================================================

@app.get(
    "/me",
    tags=["Authentication"]
)
def get_current_user(
    user: User = Depends(
        get_authenticated_user
    )
):

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email
    }


# ==================================================
# CREATE MARINE PROFILE
# ==================================================

@app.post(
    "/profile",
    response_model=MarineProfileResponse,
    tags=["Marine Profile"]
)
def create_profile(

    profile_data: MarineProfileCreate,

    user: User = Depends(
        get_authenticated_user
    ),

    db: Session = Depends(get_db)
):

    existing_profile = db.query(
        MarineProfile
    ).filter(
        MarineProfile.user_id == user.id
    ).first()

    if existing_profile:

        raise HTTPException(
            status_code=400,
            detail="Marine profile already exists"
        )

    profile = MarineProfile(

        user_id=user.id,

        user_type=profile_data.user_type,

        preferred_language=(
            profile_data.preferred_language
        ),

        # SOS emergency contact
        family_contact_name=(
            profile_data.family_contact_name
        ),

        family_contact_number=(
            profile_data.family_contact_number
        ),

        relationship=(
            profile_data.relationship
        ),

        latitude=profile_data.latitude,

        longitude=profile_data.longitude,

        boat_name=profile_data.boat_name,

        boat_type=profile_data.boat_type
    )
    db.add(profile)

    db.commit()

    db.refresh(profile)

    return profile


# ==================================================
# GET MARINE PROFILE
# ==================================================

@app.get(
    "/profile",
    response_model=MarineProfileResponse,
    tags=["Marine Profile"]
)
def get_profile(

    user: User = Depends(
        get_authenticated_user
    ),

    db: Session = Depends(get_db)
):

    profile = db.query(
        MarineProfile
    ).filter(
        MarineProfile.user_id == user.id
    ).first()

    if not profile:

        raise HTTPException(
            status_code=404,
            detail="Marine profile not found"
        )

    return profile

@app.post(
    "/sos",
    tags=["Emergency SOS"]
)
def send_sos(
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db)
):
    profile = db.query(
        MarineProfile
    ).filter(
        MarineProfile.user_id == user.id
    ).first()

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Marine profile not found"
        )

    if not profile.family_contact_number:
        raise HTTPException(
            status_code=400,
            detail="Emergency contact number is not configured"
        )

    return {
        "message": "SOS request received",
        "emergency_contact": profile.family_contact_number
    }

# ==================================================
# UPDATE MARINE PROFILE
# ==================================================

@app.put(
    "/profile",
    response_model=MarineProfileResponse,
    tags=["Marine Profile"]
)
def update_profile(

    profile_data: MarineProfileCreate,

    user: User = Depends(
        get_authenticated_user
    ),

    db: Session = Depends(get_db)
):

    profile = db.query(
        MarineProfile
    ).filter(
        MarineProfile.user_id == user.id
    ).first()

    if not profile:

        raise HTTPException(
            status_code=404,
            detail="Marine profile not found"
        )

    profile.user_type = (
        profile_data.user_type
    )

    profile.preferred_language = (
        profile_data.preferred_language
    )
        # SOS emergency contact
    profile.family_contact_name = (
        profile_data.family_contact_name
    )

    profile.family_contact_number = (
        profile_data.family_contact_number
    )

    profile.relationship = (
        profile_data.relationship
    )

    profile.latitude = (
        profile_data.latitude
    )

    profile.longitude = (
        profile_data.longitude
    )

    profile.boat_name = (
        profile_data.boat_name
    )

    profile.boat_type = (
        profile_data.boat_type
    )

    db.commit()

    db.refresh(profile)

    return profile


# ==================================================
# GET CURRENT MARINE LOCATION
# ==================================================

@app.get(
    "/location",
    tags=["Marine Location"]
)
def get_location(

    user: User = Depends(
        get_authenticated_user
    ),

    db: Session = Depends(get_db)
):

    profile = db.query(
        MarineProfile
    ).filter(
        MarineProfile.user_id == user.id
    ).first()

    if not profile:

        raise HTTPException(
            status_code=404,
            detail="Marine profile not found"
        )

    if (
        profile.latitude is None
        or profile.longitude is None
    ):

        raise HTTPException(
            status_code=404,
            detail="Location not available"
        )

    return {
        "user_id": user.id,
        "latitude": profile.latitude,
        "longitude": profile.longitude
    }