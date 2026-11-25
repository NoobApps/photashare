from datetime import datetime, timezone
from functools import wraps
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.models import User, RoleEnum, BlacklistedToken

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    blacklisted = db.query(BlacklistedToken).filter(BlacklistedToken.token == token).first()
    if blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked (logged out)",
        )

    try:
        payload = decode_access_token(token)
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except ValueError:
        raise credentials_exception

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated (banned)",
        )
    return user


def require_roles(*allowed_roles: RoleEnum):
    """FastAPI decorator for checking user roles on route handlers."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_user: User | None = kwargs.get("current_user")
            if current_user is None or current_user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions for this action",
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator


def cleanup_expired_blacklist(db: Session) -> None:
    now = datetime.now(timezone.utc)
    db.query(BlacklistedToken).filter(BlacklistedToken.expires_at < now).delete()
    db.commit()
