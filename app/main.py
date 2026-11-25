from pathlib import Path
from fastapi import FastAPI, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.session import Base, engine, get_db
from app.models.models import Photo
from app.api.routes import auth, users, photos, comments, ratings, ui
from app.api.routes.ui import _get_optional_ui_user

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="PhotoShare REST API",
    description="REST API застосунок для обміну світлинами, трансформацій через Cloudinary, QR-кодів, коментарів та оцінок.",
    version="1.0.0",
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(photos.router)
app.include_router(comments.router)
app.include_router(ratings.router)
app.include_router(ui.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, db: Session = Depends(get_db)):
    user, _ = _get_optional_ui_user(request, db)
    photos = db.query(Photo).order_by(Photo.created_at.desc()).all() if user else []
    htmx_headers = {"X-Requested-With": "HTMX"}
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "user": user,
            "photos": photos,
            "htmx_headers": htmx_headers,
        },
    )


@app.get("/api/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "PhotoShare API"}
