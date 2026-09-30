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

from fastapi.security import (
    HTTPBearer,
    HTTPAuthorizationCredentials
)

from sqlalchemy.orm import Session

from passlib.context import CryptContext

from jose import jwt, JWTError

from database import (
    engine,
    Base,
    get_db
)

from models import (
    User,
    MarineProfile
)

from schemas import (
    RegisterRequest,
    LoginRequest,
    MarineProfileCreate,
    MarineProfileResponse
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
app.include_router(satellite_router)
app.include_router(sst_router)
app.include_router(pfz_router)
app.include_router(risk_router)
app.include_router(risk_router)
if pfz_router is not None:
    app.include_router(pfz_router)
# ==================================================
# PASSWORD HASHING
# ==================================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
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
# REGISTER
# ==================================================

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

    hashed_password = pwd_context.hash(
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

    return {
        "message": "User registered successfully",
        "user_id": new_user.id,
        "name": new_user.name,
        "email": new_user.email
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

    password_correct = pwd_context.verify(
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