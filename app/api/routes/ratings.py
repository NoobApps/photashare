from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import User, Photo, Rating, RoleEnum
from app.schemas.schemas import RatingCreate, RatingResponse
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/api/ratings", tags=["Ratings"])


def _serialize_rating(rating: Rating) -> RatingResponse:
    return RatingResponse(
        id=rating.id,
        score=rating.score,
        user_id=rating.user_id,
        username=rating.user.username,
        photo_id=rating.photo_id,
        created_at=rating.created_at,
    )


@router.post("/photo/{photo_id}", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
def rate_photo(
    photo_id: int,
    rating_in: RatingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    if photo.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot rate your own photo")

    existing = db.query(Rating).filter(Rating.photo_id == photo_id, Rating.user_id == current_user.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already rated this photo")

    rating = Rating(score=rating_in.score, user_id=current_user.id, photo_id=photo_id)
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return _serialize_rating(rating)


@router.get("/photo/{photo_id}", response_model=list[RatingResponse])
@require_roles(RoleEnum.moderator, RoleEnum.admin)
def list_photo_ratings(
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return [_serialize_rating(r) for r in photo.ratings]


@router.delete("/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_roles(RoleEnum.moderator, RoleEnum.admin)
def delete_rating(
    rating_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rating = db.query(Rating).filter(Rating.id == rating_id).first()
    if not rating:
        raise HTTPException(status_code=404, detail="Rating not found")

    db.delete(rating)
    db.commit()
