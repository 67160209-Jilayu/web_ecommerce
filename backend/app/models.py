"""โครงสร้างตารางฐานข้อมูล (SQLModel)

Entity ที่ดึงจาก User Journey "อีคอมเมิร์ซ — ค้นหาและสั่งซื้อสินค้า":
- User      ผู้ใช้ 1 คนเป็นได้ทั้งผู้ซื้อและผู้ขาย (เปิดร้านได้ 1 ร้าน)
- Shop      ร้านค้า ผูกกับเจ้าของผ่าน owner_id (unique = 1 คน 1 ร้าน)
            Pain Point ในเอกสาร: "ไม่รู้จะเชื่อร้านไหน" จึงเก็บ rating/is_verified แยกจากสินค้า
- Category  หมวดหมู่สินค้า
- Product   สินค้า (1 ร้านมีได้หลายสินค้า) — ลบ = ปิดขาย (is_active) เพราะ OrderItem อ้างอิงอยู่
- ProductMedia  รูป/วิดีโอของสินค้า (1 สินค้าหลายสื่อ)
- Cart/CartItem ตะกร้า ผูกกับ browser ผ่าน token, ผูกกับ user เมื่อล็อกอิน
- Order/OrderItem  คำสั่งซื้อ — 1 order = 1 ร้าน (ตะกร้าหลายร้านจะถูกแยกออเดอร์ตอน checkout
                   เพราะแต่ละร้านจัดส่งแยกกัน สถานะจึงต้องแยก)
- Review    รีวิว ผูกกับ order_item_id (unique) = รีวิวได้เมื่อซื้อจริงและได้รับของแล้วเท่านั้น
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------- สถานะออเดอร์ / วิธีชำระเงิน (ใช้เป็น str ธรรมดาเพื่อให้ SQLModel จัดการง่าย) ----------

class OrderStatus:
    PENDING_PAYMENT = "PENDING_PAYMENT"  # รอชำระเงิน
    PAID = "PAID"                        # ชำระแล้ว รอร้านจัดส่ง
    SHIPPED = "SHIPPED"                  # ร้านจัดส่งแล้ว
    DELIVERED = "DELIVERED"              # ผู้ซื้อกดรับของแล้ว
    COMPLETED = "COMPLETED"              # รีวิวครบแล้ว
    CANCELLED = "CANCELLED"              # ยกเลิก (คืน stock แล้ว)


class PaymentMethod:
    COD = "COD"                      # เก็บเงินปลายทาง
    BANK_TRANSFER = "BANK_TRANSFER"  # โอนธนาคาร
    CARD = "CARD"                    # บัตรเครดิต/เดบิต

    ALL = (COD, BANK_TRANSFER, CARD)


# ---------- User ----------

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    name: str


class User(UserBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=utcnow)

    shop: Optional["Shop"] = Relationship(back_populates="owner")


# ---------- Shop ----------

class Shop(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id", unique=True)
    name: str
    description: str = ""
    rating: float = 0.0        # denormalized: คำนวณจาก Review จริง
    review_count: int = 0
    is_verified: bool = False
    created_at: datetime = Field(default_factory=utcnow)

    owner: Optional[User] = Relationship(back_populates="shop")
    products: list["Product"] = Relationship(back_populates="shop")


# ---------- Category ----------

class Category(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    icon: str = "📦"

    products: list["Product"] = Relationship(back_populates="category")


# ---------- Product ----------

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    shop_id: Optional[int] = Field(default=None, foreign_key="shop.id")
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")

    name: str
    price: int
    original_price: Optional[int] = None
    description: str = ""
    stock: int = 0
    free_shipping: bool = False

    image: str = "📦"                      # emoji fallback เมื่อยังไม่อัปโหลดรูป
    cover_url: Optional[str] = None        # denormalized: URL รูปแรก ใช้แสดงในหน้า list ให้เร็ว

    rating: float = 0.0                    # denormalized จาก Review
    review_count: int = 0
    sold: int = 0                          # เพิ่มเมื่อออเดอร์ถูกชำระเงิน

    is_active: bool = True                 # ลบ = ปิดขาย (soft delete)
    created_at: datetime = Field(default_factory=utcnow)

    shop: Optional[Shop] = Relationship(back_populates="products")
    category: Optional[Category] = Relationship(back_populates="products")
    media: list["ProductMedia"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"order_by": "ProductMedia.sort_order"},
    )


class ProductMedia(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id")
    url: str
    media_type: str = "image"   # image | video
    sort_order: int = 0

    product: Optional[Product] = Relationship(back_populates="media")


# ---------- Cart ----------

class Cart(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default_factory=lambda: uuid.uuid4().hex, unique=True, index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    items: list["CartItem"] = Relationship(back_populates="cart")


class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_id: int = Field(foreign_key="cart.id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int = 1

    cart: Optional[Cart] = Relationship(back_populates="items")
    product: Optional[Product] = Relationship()


# ---------- Order ----------

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_number: str = Field(unique=True, index=True)
    buyer_id: int = Field(foreign_key="user.id", index=True)
    shop_id: int = Field(foreign_key="shop.id", index=True)

    status: str = OrderStatus.PENDING_PAYMENT
    payment_method: str = PaymentMethod.COD

    subtotal: int = 0
    shipping_fee: int = 0
    total: int = 0

    recipient_name: str
    recipient_phone: str
    address: str
    note: str = ""

    created_at: datetime = Field(default_factory=utcnow)
    paid_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    buyer: Optional[User] = Relationship()
    shop: Optional[Shop] = Relationship()
    items: list["OrderItem"] = Relationship(back_populates="order")


class OrderItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    product_id: int = Field(foreign_key="product.id")

    # snapshot ข้อมูลสินค้า ณ ตอนสั่งซื้อ — ถ้าร้านแก้ราคา/ชื่อทีหลัง ออเดอร์เก่าต้องไม่เปลี่ยนตาม
    product_name: str
    product_price: int
    product_image: str = "📦"
    product_cover_url: Optional[str] = None

    quantity: int = 1
    subtotal: int = 0

    order: Optional[Order] = Relationship(back_populates="items")
    product: Optional[Product] = Relationship()
    review: Optional["Review"] = Relationship(back_populates="order_item")


# ---------- Review ----------

class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    shop_id: int = Field(foreign_key="shop.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    # unique = 1 รายการสินค้าที่ซื้อ รีวิวได้ครั้งเดียว
    order_item_id: int = Field(foreign_key="orderitem.id", unique=True)

    rating: int = 5
    comment: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    user: Optional[User] = Relationship()
    order_item: Optional[OrderItem] = Relationship(back_populates="review")
