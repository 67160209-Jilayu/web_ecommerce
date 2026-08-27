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

# โฟลเดอร์เก็บไฟล์ที่ผู้ขายอัปโหลด — ตอน deploy ต้องชี้ไปที่ persistent disk/volume
# ไม่งั้นไฟล์จะหายทุกครั้งที่ deploy ใหม่ (ดู docs/deployment.md)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))

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
