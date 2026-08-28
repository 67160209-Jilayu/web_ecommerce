"""จัดการไฟล์ที่ผู้ขายอัปโหลด (รูป/วิดีโอสินค้า)

รองรับ 2 ที่เก็บ เลือกอัตโนมัติจากค่าตั้งค่า:

1. Cloudinary — ใช้เมื่อตั้งค่า CLOUDINARY_* ไว้ เหมาะกับตอน deploy จริง
   เพราะไฟล์อยู่บนคลาวด์ ไม่หายเวลาเซิร์ฟเวอร์รีสตาร์ต และมี CDN ให้โหลดเร็ว
2. ดิสก์ในเครื่อง — ใช้เมื่อไม่ได้ตั้งค่า Cloudinary เหมาะกับตอนพัฒนา
   เพราะรันได้โดยไม่ต้องต่อเน็ตหรือสมัครบัญชีอะไร

โมดูลนี้ซ่อนความต่างไว้ข้างใน ส่วนอื่นของระบบเรียกแค่ save_upload() กับ delete_files()
โดยไม่ต้องรู้ว่าไฟล์ไปอยู่ที่ไหน
"""
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Optional

from app import config

UPLOAD_DIR = config.UPLOAD_DIR
UPLOAD_URL_PREFIX = "/uploads/"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =====================================================================
# ตั้งค่า Cloudinary (ทำครั้งเดียวตอน import)
# =====================================================================

_cloudinary = None
_cloudinary_uploader = None
_cloudinary_ready = False

if config.USE_CLOUDINARY:
    try:
        import cloudinary as _cl
        import cloudinary.uploader as _cl_uploader

        if config.CLOUDINARY_URL:
            # SDK อ่านค่าจาก environment variable CLOUDINARY_URL ให้เอง
            _cl.config(secure=True)
        else:
            _cl.config(
                cloud_name=config.CLOUDINARY_CLOUD_NAME,
                api_key=config.CLOUDINARY_API_KEY,
                api_secret=config.CLOUDINARY_API_SECRET,
                secure=True,
            )
        _cloudinary = _cl
        _cloudinary_uploader = _cl_uploader
        _cloudinary_ready = True
    except Exception as err:  # ไลบรารีไม่มีหรือค่าตั้งค่าผิด
        print(f"[คำเตือน] ตั้งค่า Cloudinary ไม่สำเร็จ ({err}) — จะเก็บไฟล์ลงดิสก์แทน", flush=True)


def backend_name() -> str:
    """ชื่อที่เก็บไฟล์ที่ใช้อยู่จริง — ใช้แสดงตอน startup และในหน้า health"""
    return "cloudinary" if _cloudinary_ready else "local-disk"


# =====================================================================
# บันทึกไฟล์
# =====================================================================

def save_upload(source: Path, media_type: str, extension: str) -> str:
    """ย้ายไฟล์ที่รับมา (ไฟล์ชั่วคราว) ไปเก็บถาวร แล้วคืน URL ที่ใช้แสดงผลได้

    media_type: "image" หรือ "video"
    extension : นามสกุลไฟล์รวมจุด เช่น ".jpg"
    """
    if _cloudinary_ready:
        return _save_to_cloudinary(source, media_type)
    return _save_to_disk(source, extension)


def _save_to_cloudinary(source: Path, media_type: str) -> str:
    result = _cloudinary_uploader.upload(
        str(source),
        folder=config.CLOUDINARY_FOLDER,
        # ให้ Cloudinary จัดการชนิดไฟล์เอง รองรับทั้งรูปและวิดีโอ
        resource_type="video" if media_type == "video" else "image",
        # ตั้งชื่อเองเพื่อกันชนกับไฟล์เดิม และไม่เอาชื่อไฟล์จากผู้ใช้มาใช้ตรงๆ
        public_id=uuid.uuid4().hex,
        overwrite=False,
        unique_filename=False,
        use_filename=False,
    )
    return result["secure_url"]


def _save_to_disk(source: Path, extension: str) -> str:
    filename = f"{uuid.uuid4().hex}{extension}"
    shutil.move(str(source), str(UPLOAD_DIR / filename))
    return f"{UPLOAD_URL_PREFIX}{filename}"


# =====================================================================
# ลบไฟล์
# =====================================================================

def path_from_url(url: str) -> Optional[Path]:
    """แปลง URL ของไฟล์ในเครื่อง (/uploads/xxx.jpg) เป็น path จริงบนดิสก์

    คืน None ถ้า URL ไม่ได้ชี้มาที่โฟลเดอร์อัปโหลดของเรา หรือพยายามหลุดออกนอกโฟลเดอร์
    (กัน path traversal จาก URL ที่ถูกแก้ในฐานข้อมูล)
    """
    if not url or not url.startswith(UPLOAD_URL_PREFIX):
        return None

    candidate = (UPLOAD_DIR / url[len(UPLOAD_URL_PREFIX):]).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return candidate


def _cloudinary_ref(url: str) -> Optional[tuple]:
    """ดึง (public_id, resource_type) จาก URL ของ Cloudinary เพื่อใช้ตอนสั่งลบ

    รูปแบบ URL: https://res.cloudinary.com/<cloud>/<resource_type>/upload/<v123>/<folder>/<id>.<ext>
    คืน None ถ้าไม่ใช่ URL ของ Cloudinary
    """
    if "res.cloudinary.com" not in url or "/upload/" not in url:
        return None

    resource_type = "video" if "/video/upload/" in url else "image"
    tail = url.split("/upload/", 1)[1]

    parts = tail.split("/")
    # ตัดส่วนเลขเวอร์ชัน (v1712345678) ที่ Cloudinary ใส่มาให้ ถ้ามี
    if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
        parts = parts[1:]
    if not parts:
        return None

    public_id = "/".join(parts)
    if "." in public_id.rsplit("/", 1)[-1]:
        public_id = public_id.rsplit(".", 1)[0]   # ตัดนามสกุลไฟล์ออก
    return public_id, resource_type


def delete_files(urls: Iterable[str]) -> int:
    """ลบไฟล์ตาม URL ที่ให้มา คืนจำนวนไฟล์ที่ลบได้จริง

    ผู้เรียกต้องมั่นใจแล้วว่าไม่มีสินค้าชิ้นไหนอ้างอิง URL เหล่านี้อยู่
    ลบไม่สำเร็จจะไม่โยน error ออกไป เพราะไม่ควรทำให้การบันทึกสินค้าล้มเหลว
    """
    removed = 0
    for url in urls:
        ref = _cloudinary_ref(url)
        if ref is not None:
            if not _cloudinary_ready:
                continue      # ไม่มีการตั้งค่า Cloudinary แล้ว ลบไม่ได้ ปล่อยไว้
            public_id, resource_type = ref
            try:
                _cloudinary_uploader.destroy(public_id, resource_type=resource_type)
                removed += 1
            except Exception:
                pass
            continue

        path = path_from_url(url)
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            removed += 1   # หายไปแล้ว ถือว่าสำเร็จ
        except OSError:
            pass
    return removed
