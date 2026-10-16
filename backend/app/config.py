"""ค่าตั้งค่าทั้งหมดของแอป อ่านจาก environment variable ที่เดียว

แยกออกมาเพื่อให้ตอน deploy จริงเปลี่ยนพฤติกรรมได้โดยไม่ต้องแก้โค้ด และเพื่อให้
ตรวจความปลอดภัยก่อนแอปเริ่มทำงาน (fail fast ดีกว่าปล่อยให้ขึ้น production ด้วยค่า dev)
"""
import os
from datetime import date
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
# ค่าเริ่มต้น = <โฟลเดอร์ที่มี app/>/uploads → ใน Docker คือ /app/uploads (เหมือนเดิม)
# รันในเครื่องโดยไม่ใช้ Docker จะเป็น backend/uploads
UPLOAD_DIR = Path(
    os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent.parent / "uploads"))
)

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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ---------- กฎราคาก่อนลด / notice ตะกร้า (เฟส 1) ----------
# อ่านจาก env ตอน import แต่โค้ดอ้างผ่าน `config.<ชื่อ>` ทุกครั้ง จึง monkeypatch ในเทสต์ได้

PRICE_REF_WINDOW_DAYS = int(os.getenv("PRICE_REF_WINDOW_DAYS", "30"))      # ราคาต่ำสุดกี่วันก่อนเริ่มลด
# ราคาต้องใช้จริงรวม ≥ เท่านี้วันในหน้าต่าง 30 วัน ถึงนับเป็น "ราคาก่อนลด" ได้ (0 = ปิดกฎนี้)
PRICE_REF_MIN_DAYS = float(os.getenv("PRICE_REF_MIN_DAYS", "7"))
PRICE_RAISE_WINDOW_DAYS = int(os.getenv("PRICE_RAISE_WINDOW_DAYS", "14"))  # ดูการขึ้นราคาย้อนหลังกี่วัน
PRICE_RAISE_PERCENT = float(os.getenv("PRICE_RAISE_PERCENT", "15"))        # ขึ้น ≥ เท่านี้ % = ซ่อน % ส่วนลด

# ช่วงผ่อนผัน: ระหว่างนี้แค่เตือนใน dashboard ผู้ขาย ยังไม่ซ่อน % ส่วนลดบนหน้าเว็บ
# PRICE_GRACE_ENABLED=false = บังคับใช้กฎทันที (ไม่มีช่วงผ่อนผัน)
PRICE_GRACE_ENABLED = _env_bool("PRICE_GRACE_ENABLED", True)
PRICE_GRACE_START = date.fromisoformat(os.getenv("PRICE_GRACE_START", "2026-10-03"))
PRICE_GRACE_DAYS = int(os.getenv("PRICE_GRACE_DAYS", "30"))

# notice ราคาลดในตะกร้า: ลด ≥ 3% หรือ ≥ 20 บาท (อย่างใดอย่างหนึ่ง) จากราคาตอนใส่ตะกร้า
CART_NOTICE_MIN_PERCENT = float(os.getenv("CART_NOTICE_MIN_PERCENT", "3"))
CART_NOTICE_MIN_BAHT = int(os.getenv("CART_NOTICE_MIN_BAHT", "20"))


# ---------- LLM (เฟส 2–4) ----------
# LLM_PROVIDER: auto (gemini ถ้ามี key ไม่งั้น none) | gemini | fake | none
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()   # อ่านจาก env เท่านั้น ห้ามเขียนในโค้ด
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash-lite")  # เปลี่ยนรุ่นได้โดยไม่ต้องแก้โค้ด
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))


# ---------- แชทช่วยช้อป (เฟส 3) — สวิตช์/การ rollout ถูกทับได้จากตาราง app_setting (ดู app/settings.py)
CHAT_ENABLED = _env_bool("CHAT_ENABLED", True)
CHAT_ROLLOUT_PERCENT = int(os.getenv("CHAT_ROLLOUT_PERCENT", "100"))   # production เริ่มที่ 5
CHAT_MAX_CHARS = int(os.getenv("CHAT_MAX_CHARS", "500"))
CHAT_DAILY_USER = int(os.getenv("CHAT_DAILY_USER", "30"))
CHAT_DAILY_GUEST = int(os.getenv("CHAT_DAILY_GUEST", "5"))
CHAT_MIN_INTERVAL_SEC = float(os.getenv("CHAT_MIN_INTERVAL_SEC", "3"))
CHAT_HISTORY_MESSAGES = int(os.getenv("CHAT_HISTORY_MESSAGES", "6"))
CHAT_MAX_PRODUCTS = int(os.getenv("CHAT_MAX_PRODUCTS", "10"))
CHAT_MAX_CARDS = int(os.getenv("CHAT_MAX_CARDS", "5"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "300"))
CHAT_CACHE_HOURS = float(os.getenv("CHAT_CACHE_HOURS", "6"))
CHAT_LOG_DAYS = int(os.getenv("CHAT_LOG_DAYS", "30"))


# ---------- เฟส 4: สรุปด้วยโมเดล / จับคู่ "อาจเป็นรุ่นเดียวกัน" / ค้นหาตามความหมาย
REVIEW_SUMMARY_MIN_REVIEWS = int(os.getenv("REVIEW_SUMMARY_MIN_REVIEWS", "3"))
FUZZY_MATCH_THRESHOLD = float(os.getenv("FUZZY_MATCH_THRESHOLD", "0.6"))
FUZZY_MAX_RESULTS = int(os.getenv("FUZZY_MAX_RESULTS", "3"))
FUZZY_NAME_WEIGHT = float(os.getenv("FUZZY_NAME_WEIGHT", "0.4"))   # ต้องน้อยกว่า threshold เสมอ (กันยัดชื่อ)
FUZZY_BRAND_WEIGHT = float(os.getenv("FUZZY_BRAND_WEIGHT", "0.25"))
FUZZY_SPEC_WEIGHT = float(os.getenv("FUZZY_SPEC_WEIGHT", "0.35"))
SEMANTIC_SEARCH = _env_bool("SEMANTIC_SEARCH", False)               # app_setting "semantic_search" ทับได้
SEMANTIC_MIN_SCORE = float(os.getenv("SEMANTIC_MIN_SCORE", "0.55"))
SEMANTIC_MAX_RESULTS = int(os.getenv("SEMANTIC_MAX_RESULTS", "10"))
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "gemini-embedding-001")


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
