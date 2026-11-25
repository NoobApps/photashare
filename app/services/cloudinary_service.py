import io
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import qrcode
from fastapi import UploadFile
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)

ALLOWED_TRANSFORMATIONS: dict[str, dict] = {
    "grayscale": {"effect": "grayscale"},
    "sepia": {"effect": "sepia:80"},
    "thumbnail_300": {"width": 300, "height": 300, "crop": "fill", "gravity": "auto"},
    "avatar_circle": {"width": 250, "height": 250, "crop": "thumb", "gravity": "face", "radius": "max"},
    "blur_light": {"effect": "blur:200"},
}


def upload_image(file: UploadFile) -> tuple[str, str]:
    result = cloudinary.uploader.upload(file.file, folder="photoshare")
    return result["secure_url"], result["public_id"]


def delete_image(public_id: str) -> None:
    cloudinary.uploader.destroy(public_id)


def build_transformed_url(public_id: str, preset: str) -> str:
    options = ALLOWED_TRANSFORMATIONS[preset]
    url, _ = cloudinary.utils.cloudinary_url(public_id, **options)
    return url


def generate_qr_png(target_url: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
