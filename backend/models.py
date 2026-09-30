from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


# ==================================================
# USER
# ==================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

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

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    user_type = Column(String, nullable=False)

    preferred_language = Column(
        String,
        default="English",
        nullable=False
    )

    latitude = Column(Float, nullable=True)

    longitude = Column(Float, nullable=True)

    boat_name = Column(String, nullable=True)

    boat_type = Column(String, nullable=True)

    user = relationship(
        "User",
        back_populates="marine_profile"
    )