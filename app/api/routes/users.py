from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import User, RoleEnum
from app.schemas.schemas import UserPublicProfile, UserSelfResponse, UserSelfUpdate
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/me", response_model=UserSelfResponse)
def read_own_profile(current_user: User = Depends(get_current_user)):
    return UserSelfResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        bio=current_user.bio,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        photos_count=len(current_user.photos),
    )


@router.put("/me", response_model=UserSelfResponse)
def update_own_profile(
    update_in: UserSelfUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if update_in.full_name is not None:
        current_user.full_name = update_in.full_name
    if update_in.bio is not None:
        current_user.bio = update_in.bio
    db.commit()
    db.refresh(current_user)
    return UserSelfResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        bio=current_user.bio,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        photos_count=len(current_user.photos),
    )


@router.get("/{username}", response_model=UserPublicProfile)
def get_public_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserPublicProfile(
        username=user.username,
        full_name=user.full_name,
        bio=user.bio,
        role=user.role,
        created_at=user.created_at,
        photos_count=len(user.photos),
    )


@router.patch("/{username}/ban", response_model=UserSelfResponse)
@require_roles(RoleEnum.admin)
def set_user_active_status(
    username: str,
    is_active: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Admin cannot ban themselves")

    user.is_active = is_active
    db.commit()
    db.refresh(user)
    return UserSelfResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        bio=user.bio,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        photos_count=len(user.photos),
    )
