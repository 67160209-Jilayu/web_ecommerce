"""โครงสร้างตารางฐานข้อมูล (SQLModel)

Entity หลักที่ดึงจาก User Journey "อีคอมเมิร์ซ — ค้นหาและสั่งซื้อสินค้า":
- Shop (ร้านค้า) — Pain Point ในเอกสาร: "สินค้าปลอมหรือไม่ตรงปก ไม่รู้จะเชื่อร้านไหน"
  จึงแยกร้านค้าเป็น entity ของตัวเอง เก็บ rating/is_verified ไว้ให้ตรวจสอบได้
- Product (สินค้า) — 1 ร้านมีได้หลายสินค้า (one-to-many)
"""
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class ShopBase(SQLModel):
    name: str
    rating: float = 0.0
    is_verified: bool = False


class Shop(ShopBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    products: list["Product"] = Relationship(back_populates="shop")


class ProductBase(SQLModel):
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


class Product(ProductBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shop_id: Optional[int] = Field(default=None, foreign_key="shop.id")

    shop: Optional[Shop] = Relationship(back_populates="products")
