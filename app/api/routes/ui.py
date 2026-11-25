from datetime import datetime, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Form, Request, Response, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token
from app.db.session import get_db
from app.models.models import User, Photo, Tag, Comment, Rating, TransformedLink, BlacklistedToken, RoleEnum
from app.services.cloudinary_service import upload_image, delete_image, build_transformed_url

router = APIRouter(prefix="/ui", tags=["HTMX UI"])
templates = Jinja2Templates(directory="app/templates")

COOKIE_NAME = "ps_access_token"


def _get_optional_ui_user(request: Request, db: Session) -> tuple[User | None, str | None]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None, None
    if db.query(BlacklistedToken).filter(BlacklistedToken.token == token).first():
        return None, None
    try:
        payload = decode_access_token(token)
        username = payload.get("sub")
    except ValueError:
        return None, None
    if not username:
        return None, None
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        return None, None
    return user, token


def _require_ui_user(request: Request, db: Session) -> User:
    user, _ = _get_optional_ui_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def _query_photos(
    db: Session,
    keyword: str | None = None,
    tag: str | None = None,
    sort_by: str = "date",
    order: str = "desc",
) -> list[Photo]:
    query = db.query(Photo)
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
    return query.order_by(sort_col.asc() if order == "asc" else sort_col.desc()).distinct().all()


@router.post("/register", response_class=HTMLResponse)
def ui_register(
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        raise HTTPException(status_code=409, detail="Username or email already registered")
    role = RoleEnum.admin if db.query(User).count() == 0 else RoleEnum.user
    user = User(
        username=username,
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash(password),
        role=role,
    )
    db.add(user)
    db.commit()
    return HTMLResponse(
        f'<div class="alert alert-success">Користувача <b>{user.username}</b> створено з роллю <b>{user.role.value}</b>. Тепер увійдіть.</div>'
    )


@router.post("/login", response_class=HTMLResponse)
def ui_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is banned")
    token, _ = create_access_token(subject=user.username, role=user.role.value)
    response.set_cookie(key=COOKIE_NAME, value=token, httponly=True, samesite="lax", path="/")
    response.headers["HX-Redirect"] = "/"
    return HTMLResponse(
        '<div class="alert alert-success">Вхід виконано. Перенаправлення...</div>'
        '<script>window.location.replace("/");</script>'
    )


@router.post("/logout", response_class=HTMLResponse)
def ui_logout(request: Request, response: Response, db: Session = Depends(get_db)):
    _, token = _get_optional_ui_user(request, db)
    if token:
        payload = decode_access_token(token)
        exp_ts = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc) if exp_ts else datetime.now(timezone.utc)
        db.add(BlacklistedToken(token=token, expires_at=expires_at))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    response.headers["HX-Redirect"] = "/"
    return HTMLResponse(
        '<div class="alert alert-secondary">Ви вийшли із системи...</div>'
        '<script>window.location.replace("/");</script>'
    )


@router.post("/photos/upload", response_class=HTMLResponse)
def ui_upload_photo(
    request: Request,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    user = _require_ui_user(request, db)
    tag_objs: list[Tag] = []
    if tags:
        names = [t.strip().lower() for t in tags.split(",") if t.strip()]
        names = list(dict.fromkeys(names))
        if len(names) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 tags allowed per photo")
        for name in names:
            tag = db.query(Tag).filter(Tag.name == name).first()
            if not tag:
                tag = Tag(name=name)
                db.add(tag)
                db.flush()
            tag_objs.append(tag)

    secure_url, public_id = upload_image(file)
    photo = Photo(url=secure_url, public_id=public_id, description=description, user_id=user.id, tags=tag_objs)
    db.add(photo)
    db.commit()
    return templates.TemplateResponse(
        "partials/photos_grid.html",
        {"request": request, "user": user, "photos": _query_photos(db)},
    )


@router.get("/photos/search", response_class=HTMLResponse)
def ui_search_photos(
    request: Request,
    keyword: str | None = None,
    tag: str | None = None,
    sort_by: Literal["date", "rating"] = "date",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
):
    user = _require_ui_user(request, db)
    photos = _query_photos(db, keyword=keyword, tag=tag, sort_by=sort_by, order=order)
    return templates.TemplateResponse(
        "partials/photos_grid.html",
        {"request": request, "user": user, "photos": photos},
    )


@router.delete("/photos/{photo_id}", response_class=HTMLResponse)
def ui_delete_photo(photo_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_ui_user(request, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Not authorized to delete this photo")
    delete_image(photo.public_id)
    db.delete(photo)
    db.commit()
    return templates.TemplateResponse(
        "partials/photos_grid.html",
        {"request": request, "user": user, "photos": _query_photos(db)},
    )


@router.post("/photos/{photo_id}/rate", response_class=HTMLResponse)
def ui_rate_photo(photo_id: int, request: Request, score: int = Form(...), db: Session = Depends(get_db)):
    user = _require_ui_user(request, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.user_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot rate your own photo")
    if db.query(Rating).filter(Rating.photo_id == photo_id, Rating.user_id == user.id).first():
        raise HTTPException(status_code=409, detail="You have already rated this photo")
    db.add(Rating(score=score, user_id=user.id, photo_id=photo_id))
    db.commit()
    return templates.TemplateResponse(
        "partials/photos_grid.html",
        {"request": request, "user": user, "photos": _query_photos(db)},
    )


@router.get("/photos/{photo_id}/details", response_class=HTMLResponse)
def ui_photo_details(photo_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_ui_user(request, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return templates.TemplateResponse(
        "partials/photo_details.html",
        {"request": request, "user": user, "photo": photo},
    )


@router.post("/photos/{photo_id}/transform", response_class=HTMLResponse)
def ui_transform_photo(
    photo_id: int,
    request: Request,
    preset: str = Form(...),
    db: Session = Depends(get_db),
):
    user = _require_ui_user(request, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.user_id != user.id and user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Not authorized to transform this photo")
    t_url = build_transformed_url(photo.public_id, preset)
    link_obj = TransformedLink(transformed_url=t_url, transformation_params=preset, photo_id=photo.id)
    db.add(link_obj)
    db.commit()
    db.refresh(link_obj)
    base = str(request.base_url).rstrip("/")
    qr_endpoint = f"{base}/api/photos/transformed/{link_obj.slug}/qr"
    return templates.TemplateResponse(
        "partials/qr_box.html",
        {"request": request, "link": link_obj, "qr_endpoint": qr_endpoint},
    )


@router.post("/photos/{photo_id}/comments", response_class=HTMLResponse)
def ui_add_comment(photo_id: int, request: Request, text: str = Form(...), db: Session = Depends(get_db)):
    user = _require_ui_user(request, db)
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    db.add(Comment(text=text, user_id=user.id, photo_id=photo.id))
    db.commit()
    db.refresh(photo)
    return templates.TemplateResponse(
        "partials/photo_details.html",
        {"request": request, "user": user, "photo": photo},
    )


@router.delete("/comments/{comment_id}", response_class=HTMLResponse)
def ui_delete_comment(comment_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_ui_user(request, db)
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if user.role not in (RoleEnum.moderator, RoleEnum.admin):
        raise HTTPException(status_code=403, detail="Only moderators and admins can delete comments")
    photo_id = comment.photo_id
    db.delete(comment)
    db.commit()
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    return templates.TemplateResponse(
        "partials/photo_details.html",
        {"request": request, "user": user, "photo": photo},
    )
