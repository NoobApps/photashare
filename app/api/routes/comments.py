from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import User, Photo, Comment, RoleEnum
from app.schemas.schemas import CommentCreate, CommentUpdate, CommentResponse
from app.api.deps import get_current_user, require_roles

router = APIRouter(prefix="/api/comments", tags=["Comments"])


def _serialize_comment(comment: Comment) -> CommentResponse:
    return CommentResponse(
        id=comment.id,
        text=comment.text,
        author_username=comment.author.username,
        photo_id=comment.photo_id,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.get("/photo/{photo_id}", response_model=list[CommentResponse])
def list_photo_comments(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return [_serialize_comment(c) for c in photo.comments]


@router.post("/photo/{photo_id}", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
def create_comment(
    photo_id: int,
    comment_in: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    comment = Comment(text=comment_in.text, user_id=current_user.id, photo_id=photo.id)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)


@router.put("/{comment_id}", response_model=CommentResponse)
def update_own_comment(
    comment_id: int,
    comment_in: CommentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # Regular users can only edit their own comment (and cannot delete it)
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own comments")

    comment.text = comment_in.text
    db.commit()
    db.refresh(comment)
    return _serialize_comment(comment)


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_roles(RoleEnum.moderator, RoleEnum.admin)
def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    db.delete(comment)
    db.commit()
