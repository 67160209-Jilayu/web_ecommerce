"""การเชื่อมต่อฐานข้อมูลผ่าน SQLModel — PostgreSQL (Docker/production) หรือ SQLite (รันในเครื่อง/เทสต์)"""
from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    # SQLite ใช้รันในเครื่องโดยไม่ต้องมี Docker เท่านั้น (เช่น DATABASE_URL=sqlite:///./shopmarket.db)
    # ข้อจำกัด: SELECT ... FOR UPDATE ถูกละทิ้ง → กันการแย่งซื้อชิ้นสุดท้ายไม่ได้จริง
    engine = create_engine(
        DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        # ฐานข้อมูลบนคลาวด์มักตัดการเชื่อมต่อที่ปล่อยว่างนานๆ ทิ้ง (โดยเฉพาะ free tier)
        # pool_pre_ping จะทดสอบ connection ก่อนใช้ทุกครั้ง ถ้าตายแล้วจะต่อใหม่ให้เอง
        # ไม่งั้นผู้ใช้คนแรกหลังเว็บถูกปล่อยว่างจะเจอ error
        pool_pre_ping=True,
        pool_recycle=300,
    )


def create_db_and_tables() -> None:
    """สร้างตารางตาม models ทั้งหมด ถ้ายังไม่มี (เรียกตอน startup)"""
    SQLModel.metadata.create_all(engine)
    ensure_schema()


# คอลัมน์ที่เพิ่มทีหลังในตารางเดิม: (ตาราง, คอลัมน์, ชนิด SQL) — ต้อง nullable ทั้งหมด
ADDED_COLUMNS = [
    ("cartitem", "price_at_add", "INTEGER"),        # เฟส 1
    ("product", "brand", "VARCHAR"),                # เฟส 2
    ("product", "model_code", "VARCHAR"),
    ("product", "barcode", "VARCHAR"),
    ("user", "province", "VARCHAR"),
    ("order", "province", "VARCHAR"),
]


def ensure_schema() -> None:
    """เติมคอลัมน์ใหม่ให้ตารางที่มีอยู่แล้วใน DB เก่า (โปรเจกต์ยังไม่มีระบบ migration)

    create_all สร้างได้แค่ "ตารางใหม่" ไม่เพิ่มคอลัมน์ให้ตารางเดิม จึงต้อง ALTER เอง
    ทุกคอลัมน์ใน ADDED_COLUMNS เป็น nullable จึงเพิ่มได้ปลอดภัย ไม่ต้องลบข้อมูลเดิม
    (cartitem.price_at_add แถวเก่าจะถูกเติมด้วยราคาปัจจุบันใน pricing.backfill_cart_price_at_add)
    ทำซ้ำได้ไม่พัง: เช็คก่อนว่ามีคอลัมน์แล้วหรือยัง + PostgreSQL ใช้ IF NOT EXISTS กันหลาย worker ชนกัน
    """
    insp = inspect(engine)
    for table, column, sql_type in ADDED_COLUMNS:
        if column in {c["name"] for c in insp.get_columns(table)}:
            continue
        quoted = f'"{table}"'   # "user"/"order" เป็นคำสงวนของ SQL
        if IS_SQLITE:
            stmt = f"ALTER TABLE {quoted} ADD COLUMN {column} {sql_type}"
        else:
            stmt = f"ALTER TABLE {quoted} ADD COLUMN IF NOT EXISTS {column} {sql_type}"
        with engine.begin() as conn:
            conn.execute(text(stmt))


def get_session():
    """FastAPI dependency: เปิด session ใหม่ต่อ 1 request แล้วปิดให้อัตโนมัติ"""
    with Session(engine) as session:
        yield session
