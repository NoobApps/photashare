from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token
from app.db.session import get_db
from app.models.models import User, RoleEnum, BlacklistedToken
from app.schemas.schemas import UserCreate, UserSelfResponse, TokenResponse
from app.api.deps import oauth2_scheme, get_current_user, cleanup_expired_blacklist

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=UserSelfResponse, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter((User.username == user_in.username) | (User.email == user_in.email)).first():
        raise HTTPException(status_code=409, detail="Username or email already registered")

    # First user in the system is always admin
    is_first_user = db.query(User).count() == 0
    role = RoleEnum.admin if is_first_user else RoleEnum.user

    user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=get_password_hash(user_in.password),
        role=role,
    )
    db.add(user)
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
        photos_count=0,
    )


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is banned")

    token, _ = create_access_token(subject=user.username, role=user.role.value)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cleanup_expired_blacklist(db)
    payload = decode_access_token(token)
    exp_ts = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc)

    db.add(BlacklistedToken(token=token, expires_at=expires_at))
    db.commit()
    return {"detail": "Successfully logged out"}
