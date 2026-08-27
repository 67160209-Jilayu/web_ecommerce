"""รูปแบบข้อมูลรับ-ส่งผ่าน API (แยกจาก models.py ที่เป็นโครงสร้างตารางจริง)"""
from datetime import datetime
from typing import Optional

from pydantic import field_validator
from sqlmodel import SQLModel

from app.models import PaymentMethod


# ---------- Auth ----------

class UserCreate(SQLModel):
    email: str
    password: str
    name: str


class UserRead(SQLModel):
    id: int
    email: str
    name: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Category ----------

class CategoryRead(SQLModel):
    id: int
    name: str
    slug: str
    icon: str


# ---------- Shop ----------

class ShopCreate(SQLModel):
    name: str
    description: str = ""


class ShopUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None


class ShopRead(SQLModel):
    id: int
    name: str
    description: str
    rating: float
    review_count: int
    is_verified: bool
    product_count: int = 0


# ---------- Product ----------

class MediaItem(SQLModel):
    url: str
    media_type: str = "image"   # image | video


class ProductCreate(SQLModel):
    name: str
    price: int
    original_price: Optional[int] = None
    category_id: Optional[int] = None
    description: str = ""
    stock: int = 0
    free_shipping: bool = False
    image: str = "📦"
    media: list[MediaItem] = []

    @field_validator("price")
    @classmethod
    def price_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("ราคาต้องมากกว่า 0")
        return v

    @field_validator("stock")
    @classmethod
    def stock_not_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("จำนวนสินค้าต้องไม่ติดลบ")
        return v


class ProductUpdate(SQLModel):
    name: Optional[str] = None
    price: Optional[int] = None
    original_price: Optional[int] = None
    category_id: Optional[int] = None
    description: Optional[str] = None
    stock: Optional[int] = None
    free_shipping: Optional[bool] = None
    image: Optional[str] = None
    media: Optional[list[MediaItem]] = None


class ProductRead(SQLModel):
    """คงชื่อ field เดิมจากสัปดาห์ 1-4 ไว้ (shop_name แบบ flatten) เพื่อไม่ให้ frontend เดิมพัง
    แล้วเพิ่ม field ใหม่ต่อท้าย
    """

    id: int
    name: str
    price: int
    original_price: Optional[int] = None
    image: str
    cover_url: Optional[str] = None
    shop_id: Optional[int] = None
    shop_name: str
    rating: float
    review_count: int
    sold: int
    stock: int
    free_shipping: bool
    category: str
    category_id: Optional[int] = None
    description: str
    is_active: bool = True
    media: list[MediaItem] = []


# ---------- Cart ----------

class CartItemCreate(SQLModel):
    product_id: int
    quantity: int = 1


class CartItemUpdate(SQLModel):
    quantity: int


class CartItemRead(SQLModel):
    product_id: int
    name: str
    price: int
    image: str
    cover_url: Optional[str] = None
    stock: int
    quantity: int
    # หน้า checkout ใช้ 2 field นี้คำนวณค่าส่งให้ตรงกับที่ backend คิดจริง
    free_shipping: bool = False
    shop_id: Optional[int] = None
    shop_name: str = ""


class CartRead(SQLModel):
    token: str
    items: list[CartItemRead]
    total: int


# ---------- Order ----------

class CheckoutRequest(SQLModel):
    recipient_name: str
    recipient_phone: str
    address: str
    note: str = ""
    payment_method: str = PaymentMethod.COD

    @field_validator("payment_method")
    @classmethod
    def payment_method_supported(cls, v: str) -> str:
        if v not in PaymentMethod.ALL:
            raise ValueError(f"วิธีชำระเงินไม่ถูกต้อง (รองรับ: {', '.join(PaymentMethod.ALL)})")
        return v

    @field_validator("recipient_name", "recipient_phone", "address")
    @classmethod
    def not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("กรอกข้อมูลผู้รับให้ครบถ้วน")
        return v.strip()


class OrderItemRead(SQLModel):
    id: int
    product_id: int
    product_name: str
    product_price: int
    product_image: str
    product_cover_url: Optional[str] = None
    quantity: int
    subtotal: int
    reviewed: bool = False


class OrderRead(SQLModel):
    id: int
    order_number: str
    status: str
    payment_method: str
    shop_id: int
    shop_name: str
    buyer_name: str = ""
    subtotal: int
    shipping_fee: int
    total: int
    recipient_name: str
    recipient_phone: str
    address: str
    note: str
    created_at: datetime
    items: list[OrderItemRead] = []


# ---------- Review ----------

class ReviewCreate(SQLModel):
    order_item_id: int
    rating: int = 5
    comment: str = ""

    @field_validator("rating")
    @classmethod
    def rating_in_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError("คะแนนต้องอยู่ระหว่าง 1-5")
        return v


class ReviewRead(SQLModel):
    id: int
    product_id: int
    rating: int
    comment: str
    user_name: str
    created_at: datetime


# ---------- Upload ----------

class UploadResult(SQLModel):
    url: str
    media_type: str
