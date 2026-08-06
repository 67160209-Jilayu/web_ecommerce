"""โครงสร้างตารางฐานข้อมูล (SQLModel)

Entity หลักที่ดึงจาก User Journey "อีคอมเมิร์ซ — ค้นหาและสั่งซื้อสินค้า":
- Shop (ร้านค้า) — Pain Point ในเอกสาร: "สินค้าปลอมหรือไม่ตรงปก ไม่รู้จะเชื่อร้านไหน"
  จึงแยกร้านค้าเป็น entity ของตัวเอง เก็บ rating/is_verified ไว้ให้ตรวจสอบได้
- Product (สินค้า) — 1 ร้านมีได้หลายสินค้า (one-to-many)
- Cart / CartItem (สัปดาห์ 3) — ตะกร้าสินค้า ผูกกับ browser ผ่าน token แทน user_id ชั่วคราว
  เพราะยังไม่มีระบบล็อกอิน (รอสัปดาห์ 4) 1 ตะกร้ามีได้หลายรายการสินค้า (one-to-many)
"""
import uuid
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


class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default_factory=lambda: uuid.uuid4().hex, unique=True, index=True)

    items: list["CartItem"] = Relationship(back_populates="cart")


class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_id: int = Field(foreign_key="cart.id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int = 1

    cart: Optional[Cart] = Relationship(back_populates="items")
    product: Optional[Product] = Relationship()
