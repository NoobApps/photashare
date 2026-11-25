import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Table, Enum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db.session import Base


def utcnow():
    return datetime.now(timezone.utc)


class RoleEnum(str, enum.Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


photo_tags = Table(
    "photo_tags",
    Base.metadata,
    Column("photo_id", Integer, ForeignKey("photos.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(120), nullable=True)
    bio = Column(String(500), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.user, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    photos = relationship("Photo", back_populates="owner", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="author", cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="user", cascade="all, delete-orphan")


class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(512), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)

    photos = relationship("Photo", secondary=photo_tags, back_populates="tags")


class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    unique_slug = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False, index=True)
    url = Column(String(500), nullable=False)
    public_id = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    owner = relationship("User", back_populates="photos")

    tags = relationship("Tag", secondary=photo_tags, back_populates="photos")
    comments = relationship("Comment", back_populates="photo", cascade="all, delete-orphan")
    ratings = relationship("Rating", back_populates="photo", cascade="all, delete-orphan")
    transformed_links = relationship("TransformedLink", back_populates="photo", cascade="all, delete-orphan")


class TransformedLink(Base):
    __tablename__ = "transformed_links"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False, index=True)
    transformed_url = Column(String(600), nullable=False)
    transformation_params = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)
    photo = relationship("Photo", back_populates="transformed_links")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)

    author = relationship("User", back_populates="comments")
    photo = relationship("Photo", back_populates="comments")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("user_id", "photo_id", name="uq_user_photo_rating"),)

    id = Column(Integer, primary_key=True, index=True)
    score = Column(Integer, nullable=False)  # 1..5
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    photo_id = Column(Integer, ForeignKey("photos.id", ondelete="CASCADE"), nullable=False)

    user = relationship("User", back_populates="ratings")
    photo = relationship("Photo", back_populates="ratings")
