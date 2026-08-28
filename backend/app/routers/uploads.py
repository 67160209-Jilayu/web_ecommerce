"""Router อัปโหลดรูป/วิดีโอสินค้า

รับไฟล์ → ตรวจชนิดและขนาด → ส่งให้ app/storage.py เก็บ
(จะไปอยู่บน Cloudinary หรือดิสก์ ขึ้นกับค่าตั้งค่า router ไม่ต้องรู้)
"""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app import models, schemas, storage
from app.routers.auth import get_current_user

router = APIRouter(prefix="/uploads", tags=["uploads"])

logger = logging.getLogger(__name__)

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

    # เขียนลงไฟล์ชั่วคราวก่อน เพื่อเช็คขนาดระหว่างรับโดยไม่ต้องโหลดทั้งไฟล์เข้าแรม
    tmp = tempfile.NamedTemporaryFile(suffix=extension, delete=False)
    tmp_path = Path(tmp.name)
    written = 0

    try:
        with tmp:
            while chunk := await file.read(CHUNK_SIZE):
                written += len(chunk)
                if written > max_bytes:
                    limit_mb = max_bytes // (1024 * 1024)
                    raise HTTPException(
                        status_code=400,
                        detail=f"ไฟล์ใหญ่เกินกำหนด ({media_type} ไม่เกิน {limit_mb}MB)",
                    )
                tmp.write(chunk)

        if written == 0:
            raise HTTPException(status_code=400, detail="ไฟล์ว่างเปล่า")

        url = storage.save_upload(tmp_path, media_type, extension)

    except HTTPException:
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        # ต้อง log ต้นเหตุจริงไว้เสมอ ไม่งั้นเวลาขึ้น production แล้วอัปโหลดพัง
        # จะเห็นแค่ข้อความกลางๆ หาสาเหตุไม่ได้เลย (ผู้ใช้ยังเห็นข้อความสุภาพเหมือนเดิม)
        logger.exception("อัปโหลดไฟล์ไม่สำเร็จ")
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="บันทึกไฟล์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")
    finally:
        # เก็บกวาดไฟล์ชั่วคราวเสมอ (กรณีเก็บลงดิสก์ ไฟล์ถูกย้ายไปแล้ว unlink จะไม่เจอ ซึ่งไม่เป็นไร)
        tmp_path.unlink(missing_ok=True)

    return schemas.UploadResult(url=url, media_type=media_type)
