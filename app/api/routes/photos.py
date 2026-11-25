from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query, status
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import User, Photo, Tag, Rating, TransformedLink, RoleEnum
from app.schemas.schemas import (
    PhotoResponse, PhotoUpdate, TagResponse, TransformRequest, TransformedLinkResponse
)
from app.services.cloudinary_service import (
    upload_image, delete_image, build_transformed_url, generate_qr_png
)
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/photos", tags=["Photos"])


def _serialize_photo(photo: Photo) -> PhotoResponse:
    scores = [r.score for r in photo.ratings]
    avg_rating = round(sum(scores) / len(scores), 2) if scores else None
    return PhotoResponse(
        id=photo.id,
        unique_slug=photo.unique_slug,
        url=photo.url,
        description=photo.description,
        created_at=photo.created_at,
        updated_at=photo.updated_at,
        owner_username=photo.owner.username,
        tags=[TagResponse.model_validate(t) for t in photo.tags],
        average_rating=avg_rating,
        ratings_count=len(scores),
    )


def _get_or_create_tags(db: Session, raw_tags: str | None) -> list[Tag]:
    if not raw_tags:
        return []
    names = []
    for item in raw_tags.split(","):
        clean = item.strip().lower()
        if clean and clean not in names:
            names.append(clean)

    if len(names) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 tags allowed per photo")

    tag_objects: list[Tag] = []
    for name in names:
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tag_objects.append(tag)
    return tag_objects


@router.post("/", response_model=PhotoResponse, status_code=status.HTTP_201_CREATED)
def upload_photo(
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None, description="Comma-separated tags, max 5"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tag_objs = _get_or_create_tags(db, tags)
    secure_url, public_id = upload_image(file)

    photo = Photo(
        url=secure_url,
        public_id=public_id,
        description=description,
        user_id=current_user.id,
        tags=tag_objs,
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return _serialize_photo(photo)


@router.get("/search", response_model=list[PhotoResponse])
def search_photos(
    keyword: str | None = Query(default=None, description="Search in description"),
    tag: str | None = Query(default=None, description="Filter by exact tag name"),
    username: str | None = Query(default=None, description="Moderator/Admin only: filter by author username"),
    sort_by: Literal["date", "rating"] = Query(default="date"),
    order: Literal["asc", "desc"] = Query(default="desc"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Photo)

    if username:
        if current_user.role not in (RoleEnum.moderator, RoleEnum.admin):
            raise HTTPException(status_code=403, detail="Only moderators and admins can filter by user")
        query = query.join(User).filter(User.username == username)

    if keyword:
        query = query.filter(Photo.description.ilike(f"%{keyword}%"))

    if tag:
        query = query.join(Photo.tags).filter(Tag.name == tag.strip().lower())

    if sort_by == "rating":
        avg_subq = (
            db.query(Rating.photo_id, func.avg(Rating.score).label("avg_score"))
            .group_by(Rating.photo_id)
            .subquery()
        )
        query = query.outerjoin(avg_subq, Photo.id == avg_subq.c.photo_id)
        sort_col = func.coalesce(avg_subq.c.avg_score, 0)
    else:
        sort_col = Photo.created_at

    query = query.order_by(sort_col.asc() if order == "asc" else sort_col.desc())
    photos = query.distinct().all()
    return [_serialize_photo(p) for p in photos]


@router.get("/{unique_slug}", response_model=PhotoResponse)
def get_photo_by_slug(unique_slug: str, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.unique_slug == unique_slug).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return _serialize_photo(photo)


@router.put("/{photo_id}", response_model=PhotoResponse)
def update_photo_description(
    photo_id: int,
    photo_in: PhotoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if photo.user_id != current_user.id and current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Not authorized to edit this photo")

    photo.description = photo_in.description
    db.commit()
    db.refresh(photo)
    return _serialize_photo(photo)


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_photo(
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if photo.user_id != current_user.id and current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this photo")

    delete_image(photo.public_id)
    db.delete(photo)
    db.commit()


@router.post("/{photo_id}/transform", response_model=TransformedLinkResponse, status_code=status.HTTP_201_CREATED)
def create_transformed_link(
    photo_id: int,
    transform_in: TransformRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if photo.user_id != current_user.id and current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Not authorized to transform this photo")

    t_url = build_transformed_url(photo.public_id, transform_in.preset)
    link_obj = TransformedLink(
        transformed_url=t_url,
        transformation_params=transform_in.preset,
        photo_id=photo.id,
    )
    db.add(link_obj)
    db.commit()
    db.refresh(link_obj)

    base = str(request.base_url).rstrip("/")
    qr_endpoint = f"{base}/api/photos/transformed/{link_obj.slug}/qr"
    return TransformedLinkResponse(
        id=link_obj.id,
        slug=link_obj.slug,
        transformed_url=link_obj.transformed_url,
        qr_code_endpoint=qr_endpoint,
        transformation_params=link_obj.transformation_params,
        created_at=link_obj.created_at,
    )


@router.get("/transformed/{slug}/view")
def view_transformed_image(slug: str, db: Session = Depends(get_db)):
    link_obj = db.query(TransformedLink).filter(TransformedLink.slug == slug).first()
    if not link_obj:
        raise HTTPException(status_code=404, detail="Transformed link not found")
    return RedirectResponse(url=link_obj.transformed_url)


@router.get("/transformed/{slug}/qr")
def get_transformed_qr_code(slug: str, request: Request, db: Session = Depends(get_db)):
    link_obj = db.query(TransformedLink).filter(TransformedLink.slug == slug).first()
    if not link_obj:
        raise HTTPException(status_code=404, detail="Transformed link not found")

    base = str(request.base_url).rstrip("/")
    mobile_view_url = f"{base}/api/photos/transformed/{link_obj.slug}/view"
    qr_buffer = generate_qr_png(mobile_view_url)
    return StreamingResponse(qr_buffer, media_type="image/png")
