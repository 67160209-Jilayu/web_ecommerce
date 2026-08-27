"""ใส่ข้อมูลตั้งต้นตอนเริ่มระบบครั้งแรก (ทำงานเฉพาะตอนฐานข้อมูลยังว่าง ไม่ทับข้อมูลเดิม)

สร้างแค่ 2 อย่าง:
1. หมวดหมู่สินค้า 6 หมวด — จำเป็นต่อระบบ เพราะฟอร์มลงขายต้องมีให้เลือก
2. บัญชีผู้ขาย 1 บัญชี พร้อมร้าน "mango" — ไม่มีสินค้าตัวอย่าง ให้ลงขายเองทั้งหมด
"""
from sqlmodel import Session, select

from app import models
from app.auth import hash_password

# บัญชีเจ้าของร้าน mango
MANGO_EMAIL = "mango@shopmarket.test"
MANGO_PASSWORD = "mango1234"
MANGO_OWNER_NAME = "เจ้าของร้าน Mango"

MANGO_SHOP_NAME = "mango"
MANGO_SHOP_DESC = "ร้าน mango — คัดของดีมาให้เลือก ส่งไว บริการเป็นกันเอง"

CATEGORIES = [
    ("ของใช้ในบ้าน", "home", "🏠"),
    ("เครื่องครัว", "kitchen", "🍳"),
    ("สุขภาพและความงาม", "beauty", "💄"),
    ("อุปกรณ์อิเล็กทรอนิกส์", "electronics", "🔌"),
    ("แฟชั่น", "fashion", "👕"),
    ("กีฬาและกลางแจ้ง", "sports", "⚽"),
]


def seed_if_empty(session: Session) -> None:
    if session.exec(select(models.Category)).first() is not None:
        return

    for name, slug, icon in CATEGORIES:
        session.add(models.Category(name=name, slug=slug, icon=icon))

    owner = models.User(
        email=MANGO_EMAIL,
        name=MANGO_OWNER_NAME,
        hashed_password=hash_password(MANGO_PASSWORD),
    )
    session.add(owner)
    session.flush()

    session.add(
        models.Shop(
            owner_id=owner.id,
            name=MANGO_SHOP_NAME,
            description=MANGO_SHOP_DESC,
            is_verified=True,
        )
    )
    session.commit()
