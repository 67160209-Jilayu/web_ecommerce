"""การเชื่อมต่อฐานข้อมูล PostgreSQL ผ่าน SQLModel"""
import os

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://appuser:apppassword@db:5432/appdb"
)

engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    """สร้างตารางตาม models ทั้งหมด ถ้ายังไม่มี (เรียกตอน startup)"""
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency: เปิด session ใหม่ต่อ 1 request แล้วปิดให้อัตโนมัติ"""
    with Session(engine) as session:
        yield session
