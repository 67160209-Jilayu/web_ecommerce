"""รูปแบบข้อมูลรับ-ส่งผ่าน API (แยกจาก models.py ที่เป็นโครงสร้างตารางจริง)"""
from typing import Optional

from sqlmodel import SQLModel


class ShopCreate(SQLModel):
    name: str
    rating: float = 0.0
    is_verified: bool = False


class ShopRead(ShopCreate):
    id: int


class ProductCreate(SQLModel):
    shop_id: int
    name: str
    price: int
    original_price: Optional[int] = None
    image: str = "📦"
    category: str = "ทั่วไป"
    description: str = ""
    rating: float = 0.0
    sold: int = 0
    stock: int = 0
    free_shipping: bool = False


class ProductRead(SQLModel):
    """คงรูปแบบ field เดิมจากตอน mock data (สัปดาห์ 1) ไว้ เพื่อไม่ต้องแก้ frontend
    ที่เขียนไว้แล้ว — flatten shop.name มาเป็น shop_name แทนการส่งเป็น object ซ้อน
    """

    id: int
    name: str
    price: int
    original_price: Optional[int] = None
    image: str
    shop_name: str
    rating: float
    sold: int
    stock: int
    free_shipping: bool
    category: str
    description: str
