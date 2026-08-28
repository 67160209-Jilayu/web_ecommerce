"""ค่าตั้งค่าทั้งหมดของแอป อ่านจาก environment variable ที่เดียว

แยกออกมาเพื่อให้ตอน deploy จริงเปลี่ยนพฤติกรรมได้โดยไม่ต้องแก้โค้ด และเพื่อให้
ตรวจความปลอดภัยก่อนแอปเริ่มทำงาน (fail fast ดีกว่าปล่อยให้ขึ้น production ด้วยค่า dev)
"""
import os
from pathlib import Path

# ค่าเดียวกับที่เขียนไว้ใน .env.example — ห้ามใช้ค่านี้บน production เด็ดขาด
DEV_SECRET_KEY = "dev-secret-key-change-in-production"

# development (ค่าเริ่มต้น) = รันในเครื่อง ผ่อนปรนได้ | production = ตรวจเข้ม
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"


def _normalize_database_url(url: str) -> str:
    """แปลง scheme ให้ SQLAlchemy 2.x อ่านได้

    บริการ hosting หลายเจ้า (Render, Heroku) แจก connection string ขึ้นต้นด้วย `postgres://`
    ซึ่ง SQLAlchemy 2.x ไม่รองรับแล้ว ต้องเป็น `postgresql://` — แปลงให้อัตโนมัติตรงนี้
    จะได้ไม่ต้องมานั่งแก้ค่าในหน้าเว็บของบริการเอง
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", "postgresql://appuser:apppassword@db:5432/appdb")
)

SECRET_KEY = os.getenv("SECRET_KEY", DEV_SECRET_KEY)

# โฟลเดอร์เก็บไฟล์ที่ผู้ขายอัปโหลด (ใช้เมื่อไม่ได้ตั้งค่า Cloudinary)
# ตอน deploy ถ้าเก็บลงดิสก์ ต้องชี้ไปที่ persistent disk/volume
# ไม่งั้นไฟล์จะหายทุกครั้งที่เซิร์ฟเวอร์รีสตาร์ต (ดู docs/deployment.md)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))

# ---------- Cloudinary (ที่เก็บรูป/วิดีโอบนคลาวด์) ----------
# ตั้งค่าอย่างใดอย่างหนึ่ง:
#   1) CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>   (ง่ายสุด ตัวแปรเดียว)
#   2) ตั้งแยกสามตัว: CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
# ถ้าไม่ตั้งเลย ระบบจะเขียนไฟล์ลงดิสก์เหมือนเดิม (สะดวกตอนรันในเครื่อง ไม่ต้องต่อเน็ต)
def _clean_cloudinary_url(raw: str) -> str:
    """ทำความสะอาดค่าที่คนกรอกมา เพราะพลาดกันบ่อยมาก 3 แบบ

    1. คัดลอกทั้งบรรทัดจาก Dashboard มา จะติด "CLOUDINARY_URL=" นำหน้ามาด้วย
    2. แทนที่ตัวอย่าง <api_key> แล้วลืมลบวงเล็บมุม < > ออก
    3. ติดเครื่องหมายคำพูดหรือช่องว่างหัวท้าย

    ทั้งสามแบบ SDK จะรับไปเงียบๆ แล้วไปพังตอนอัปโหลดจริงเป็น 401 ซึ่งหาสาเหตุยาก
    จึงเก็บกวาดให้ตรงนี้เลย
    """
    value = raw.strip().strip('"').strip("'").strip()
    if value.upper().startswith("CLOUDINARY_URL="):
        value = value.split("=", 1)[1].strip()
    return value.replace("<", "").replace(">", "").strip()


CLOUDINARY_URL = _clean_cloudinary_url(os.getenv("CLOUDINARY_URL", ""))
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip().strip("<>")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip().strip("<>")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip().strip("<>")

# โฟลเดอร์บน Cloudinary ที่จะเก็บไฟล์ของโปรเจกต์นี้ (กันปนกับโปรเจกต์อื่นในบัญชีเดียวกัน)
CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "shopmarket").strip("/")

USE_CLOUDINARY = bool(
    CLOUDINARY_URL
    or (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)
)


def cloudinary_diagnosis() -> str:
    """บอกเหตุผลว่าทำไมถึงใช้/ไม่ใช้ Cloudinary — ไม่เปิดเผยค่าลับใดๆ

    ใช้แสดงในหน้า /api/health เพื่อให้ตรวจปัญหาตอน deploy ได้เองโดยไม่ต้องเปิดดู log
    """
    if CLOUDINARY_URL:
        if not CLOUDINARY_URL.startswith("cloudinary://"):
            return "ค่า CLOUDINARY_URL ผิดรูปแบบ (ต้องขึ้นต้นด้วย cloudinary://)"
        if "@" not in CLOUDINARY_URL or ":" not in CLOUDINARY_URL.split("//", 1)[-1]:
            return "ค่า CLOUDINARY_URL ไม่ครบส่วน (ต้องเป็น cloudinary://api_key:api_secret@cloud_name)"
        return "ตั้งค่าจาก CLOUDINARY_URL"

    partial = [
        name for name, value in (
            ("CLOUDINARY_CLOUD_NAME", CLOUDINARY_CLOUD_NAME),
            ("CLOUDINARY_API_KEY", CLOUDINARY_API_KEY),
            ("CLOUDINARY_API_SECRET", CLOUDINARY_API_SECRET),
        ) if not value
    ]
    if len(partial) < 3:
        return "ตั้งค่าไม่ครบ ยังขาด: " + ", ".join(partial)

    return "ยังไม่ได้ตั้งค่า CLOUDINARY_URL ในหน้า Environment ของบริการ deploy"

# โดเมนที่เรียก API ได้ คั่นด้วยคอมมา — "*" = ทุกโดเมน
# frontend ถูก serve จาก origin เดียวกับ API อยู่แล้ว จึงตั้งให้แคบได้บน production
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
]


def validate() -> None:
    """ตรวจค่าที่ห้ามพลาดก่อนแอปเริ่มรับ request — เรียกตอน startup

    บน production ถ้า SECRET_KEY ยังเป็นค่า dev จะหยุดแอปทันที เพราะใครก็ตามที่เห็น
    โค้ดในรีโป (ซึ่งเป็น public) จะปลอม JWT เข้าบัญชีคนอื่นได้ทั้งหมด
    """
    if not IS_PRODUCTION:
        return

    if SECRET_KEY == DEV_SECRET_KEY or len(SECRET_KEY) < 32:
        raise RuntimeError(
            "SECRET_KEY ไม่ปลอดภัยสำหรับ production — ต้องตั้งเป็นค่าสุ่มยาวอย่างน้อย 32 ตัวอักษร\n"
            "สร้างค่าใหม่ด้วย: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\"\n"
            "แล้วนำไปตั้งเป็น environment variable ชื่อ SECRET_KEY ในหน้าตั้งค่าของบริการ deploy"
        )

    if not USE_CLOUDINARY:
        # ไม่หยุดแอป เพราะอาจตั้งใจใช้ persistent disk/volume แทน — แต่ต้องเตือนให้เห็นชัด
        # เพราะถ้าเก็บลงดิสก์ธรรมดาบน Render/Railway ไฟล์จะหายทุกครั้งที่เซิร์ฟเวอร์รีสตาร์ต
        print(
            "[คำเตือน] ยังไม่ได้ตั้งค่า Cloudinary — ไฟล์ที่อัปโหลดจะเก็บลงดิสก์ที่ "
            f"{UPLOAD_DIR}\n"
            "          ถ้าโฟลเดอร์นี้ไม่ใช่ persistent disk/volume รูปสินค้าจะหายทุกครั้ง"
            " ที่เซิร์ฟเวอร์รีสตาร์ต\n"
            "          วิธีตั้งค่า Cloudinary ดูที่ docs/deployment.md",
            flush=True,
        )
