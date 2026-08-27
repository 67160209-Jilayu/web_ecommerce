"""Router อัปโหลดรูป/วิดีโอสินค้า

เก็บไฟล์ลงดิสก์ที่ /app/uploads (map เป็น named volume ใน docker-compose ไม่งั้นหายตอน restart)
แล้ว serve ผ่าน static path /uploads/<ชื่อไฟล์>
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import models, schemas
from app.routers.auth import get_current_user
from app.storage import UPLOAD_DIR

router = APIRouter(prefix="/uploads", tags=["uploads"])

# ตรวจจาก content-type จริงที่เบราว์เซอร์ส่งมา ไม่เชื่อนามสกุลไฟล์ (กันไฟล์ปลอมนามสกุล)
IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
VIDEO_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024    # 5MB
MAX_VIDEO_BYTES = 50 * 1024 * 1024   # 50MB
CHUNK_SIZE = 1024 * 1024             # อ่านทีละ 1MB กันไฟล์ใหญ่กินแรมทั้งก้อน


@router.post("", response_model=schemas.UploadResult, status_code=201)
async def upload_media(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    """อัปโหลดรูปหรือวิดีโอ 1 ไฟล์ — ต้องล็อกอินก่อน คืน URL ไว้ผูกกับสินค้า"""
    content_type = (file.content_type or "").lower()

    if content_type in IMAGE_TYPES:
        media_type, extension, max_bytes = "image", IMAGE_TYPES[content_type], MAX_IMAGE_BYTES
    elif content_type in VIDEO_TYPES:
        media_type, extension, max_bytes = "video", VIDEO_TYPES[content_type], MAX_VIDEO_BYTES
    else:
        raise HTTPException(
            status_code=400,
            detail="รองรับเฉพาะรูปภาพ (jpg/png/webp/gif) และวิดีโอ (mp4/webm/mov) เท่านั้น",
        )

    # ตั้งชื่อไฟล์ใหม่ด้วย uuid ทั้งหมด — กันชื่อซ้ำและกัน path traversal จากชื่อไฟล์ที่ผู้ใช้ส่งมา
    filename = f"{uuid.uuid4().hex}{extension}"
    dest = UPLOAD_DIR / filename

    written = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    limit_mb = max_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=400,
                        detail=f"ไฟล์ใหญ่เกินกำหนด ({media_type} ไม่เกิน {limit_mb}MB)",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="บันทึกไฟล์ไม่สำเร็จ")

    if written == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")

    return schemas.UploadResult(url=f"/uploads/{filename}", media_type=media_type)
