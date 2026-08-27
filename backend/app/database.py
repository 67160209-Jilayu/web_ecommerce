"""การเชื่อมต่อฐานข้อมูล PostgreSQL ผ่าน SQLModel"""
from sqlmodel import Session, SQLModel, create_engine

from app.config import DATABASE_URL

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


def get_session():
    """FastAPI dependency: เปิด session ใหม่ต่อ 1 request แล้วปิดให้อัตโนมัติ"""
    with Session(engine) as session:
        yield session
