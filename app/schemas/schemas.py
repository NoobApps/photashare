from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from app.models.models import RoleEnum


# --- Auth & Users ---
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserSelfResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: str | None
    bio: str | None
    role: RoleEnum
    is_active: bool
    created_at: datetime
    photos_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class UserSelfUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=500)


class UserPublicProfile(BaseModel):
    username: str
    full_name: str | None
    bio: str | None
    role: RoleEnum
    created_at: datetime
    photos_count: int


# --- Tags & Photos ---
class TagResponse(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class PhotoUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=1000)


class PhotoResponse(BaseModel):
    id: int
    unique_slug: str
    url: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    owner_username: str
    tags: list[TagResponse] = []
    average_rating: float | None = None
    ratings_count: int = 0


# --- Transformations & QR ---
class TransformRequest(BaseModel):
    preset: Literal["grayscale", "sepia", "thumbnail_300", "avatar_circle", "blur_light"]


class TransformedLinkResponse(BaseModel):
    id: int
    slug: str
    transformed_url: str
    qr_code_endpoint: str
    transformation_params: str
    created_at: datetime


# --- Comments ---
class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class CommentUpdate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)


class CommentResponse(BaseModel):
    id: int
    text: str
    author_username: str
    photo_id: int
    created_at: datetime
    updated_at: datetime


# --- Ratings ---
class RatingCreate(BaseModel):
    score: int = Field(..., ge=1, le=5)


class RatingResponse(BaseModel):
    id: int
    score: int
    user_id: int
    username: str
    photo_id: int
    created_at: datetime
