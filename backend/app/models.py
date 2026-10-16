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

ระบบราคาเบื้องหลัง (เฟส 1 — ใช้ภายใน ไม่แสดงประวัติต่อผู้ซื้อ):
- SkuPriceHistory  ประวัติราคา/สถานะสต็อก ราย SKU (ระบบนี้ยังไม่มี variant จึงใช้ sku_id = product.id)
- SkuPriceRef      ค่าที่คำนวณล่วงหน้า: ราคาต่ำสุด 30 วันก่อนเริ่มลด + % ขึ้นราคาสูงสุดใน 14 วันก่อนลด
- CartPriceNotice  notice "ราคาลดลงตั้งแต่ใส่ตะกร้า" 1 แถวต่อ 1 cart_item (เฉพาะผู้ใช้ที่ล็อกอิน)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index, UniqueConstraint
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
    province: Optional[str] = None      # จังหวัดหลักของบัญชี (ใช้คำนวณค่าส่งในหน้าเทียบ) — เฟส 2
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

    # เฟส 2: ใช้จับคู่ "ร้านอื่นที่ขายรุ่นนี้" (ตรงทุกตัวเท่านั้น)
    brand: Optional[str] = None
    model_code: Optional[str] = None
    barcode: Optional[str] = Field(default=None, index=True)

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
    # ราคา ณ ตอนใส่ตะกร้า — ใช้เทียบกับราคาปัจจุบันเพื่อสร้าง notice ราคาลด
    # (คอลัมน์นี้เพิ่มทีหลัง DB เก่าจะถูกเติมให้ตอน startup ดู database.ensure_schema)
    price_at_add: Optional[int] = None

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
    province: Optional[str] = None   # จังหวัดปลายทาง (ใช้คิดค่าส่ง + เดาจังหวัดผู้ซื้อในหน้าเทียบ)

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


# ---------- ระบบราคาเบื้องหลัง (เฟส 1) ----------

class PriceSource:
    SELLER = "seller"       # ผู้ขายแก้ราคา/สต็อกเอง
    CAMPAIGN = "campaign"   # เริ่ม/จบแคมเปญ (ยังไม่มีระบบแคมเปญ เผื่อไว้)
    DYNAMIC = "dynamic"     # dynamic pricing (ยังไม่มี เผื่อไว้)
    SYSTEM = "system"       # ระบบเปลี่ยนเอง เช่น สต็อกหมดจาก checkout, คืนสต็อกตอนยกเลิก, backfill


class PriceType:
    REGULAR = "regular"     # ราคาปกติ
    DISCOUNT = "discount"   # ต่ำกว่าราคาต่ำสุด 30 วันก่อนหน้า = ถือว่ากำลังลดราคา


class SkuPriceHistory(SQLModel, table=True):
    """ประวัติราคาราย SKU ต่อร้าน — เขียนใน transaction เดียวกับที่แก้ราคา/สต็อก
    และเขียนเฉพาะตอนค่าเปลี่ยนจริง (ปิดแถวเดิมด้วย valid_to แล้วเปิดแถวใหม่)

    ใช้ภายในเท่านั้น ห้ามส่งออกไปให้ผู้ซื้อเห็น
    เวลาเก็บเป็น UTC แบบ naive (ไม่มี tzinfo) ให้ผลเหมือนกันทั้ง PostgreSQL และ SQLite
    """
    __tablename__ = "sku_price_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    sku_id: int = Field(foreign_key="product.id")
    shop_id: Optional[int] = Field(default=None, foreign_key="shop.id")
    list_price: int                 # ราคาที่ผู้ขายตั้ง
    effective_price: int            # ราคาหลังส่วนลดร้าน (ตอนนี้ยังไม่มีส่วนลดร้าน = list_price)
    price_type: str = PriceType.REGULAR
    in_stock: bool = True
    source: str = PriceSource.SELLER
    valid_from: datetime
    valid_to: Optional[datetime] = None   # None = แถวที่ใช้อยู่ปัจจุบัน


Index(
    "ix_sku_price_history_sku_valid_from",
    SkuPriceHistory.__table__.c.sku_id,
    SkuPriceHistory.__table__.c.valid_from.desc(),
)


class SkuPriceRef(SQLModel, table=True):
    """ค่าอ้างอิงที่คำนวณล่วงหน้า (หลังราคาเปลี่ยน + งานกลางคืน) — หน้าเว็บอ่านอย่างเดียว ไม่คำนวณสด"""
    __tablename__ = "sku_price_ref"

    sku_id: int = Field(foreign_key="product.id", primary_key=True)
    # ราคาต่ำสุดใน 30 วันก่อนราคาปัจจุบันเริ่มใช้ = "ราคาก่อนลด" ที่ระบบจะแสดง (ถ้าสูงกว่าราคาปัจจุบัน)
    min_30d: Optional[int] = None
    # % ขึ้นราคาสูงสุด (สะสม) ภายใน 14 วันก่อนราคาปัจจุบันเริ่มใช้
    max_increase_14d: Optional[float] = None
    # ราคาที่ใช้คำนวณแถวนี้ + เวลาที่ราคานี้เริ่มใช้ — ถ้าไม่ตรงกับ product.price แปลว่าค่ายังไม่อัปเดต
    effective_price: Optional[int] = None
    price_since: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utcnow)


class CartPriceNotice(SQLModel, table=True):
    """notice ราคาลดของสินค้าในตะกร้า — 1 แถวต่อ cart_item ไม่ส่ง push/อีเมล/LINE"""
    __tablename__ = "cart_price_notice"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    sku_id: int = Field(foreign_key="product.id", index=True)
    cart_item_id: int = Field(foreign_key="cartitem.id", unique=True)
    old_price: int      # = price_at_add
    new_price: int      # ราคาปัจจุบันตอนสร้าง/อัปเดต notice
    created_at: datetime = Field(default_factory=utcnow)
    read_at: Optional[datetime] = None


# ---------- เฟส 2: สเปกสินค้า / ค่าส่ง / เปรียบเทียบ ----------

class CategoryAttribute(SQLModel, table=True):
    """แม่แบบสเปกต่อหมวด — กำหนดชื่อ หน่วย ชนิดข้อมูล กลุ่ม ทิศทาง (มาก/น้อยดีกว่า) และความจำเป็น"""
    __tablename__ = "category_attribute"
    __table_args__ = (UniqueConstraint("category_id", "key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    category_id: int = Field(foreign_key="category.id", index=True)
    key: str
    name_th: str
    unit: Optional[str] = None
    data_type: str = "number"            # number | text | enum | bool
    options_json: Optional[str] = None   # JSON list สำหรับ enum (ลำดับ = อันดับ ถ้า better ไม่ใช่ none)
    group_name: str = "ทั่วไป"
    better: str = "none"                 # higher | lower | none
    required: bool = False
    sort: int = 0
    badge_label: Optional[str] = None    # ป้ายบนหัวคอลัมน์เมื่อชนะแถวนี้ เช่น "แบตอึดที่สุด"


class ProductAttributeValue(SQLModel, table=True):
    """ค่าสเปกของสินค้า — ตัวเลขเก็บเป็น number เพื่อกรองและเทียบได้"""
    __tablename__ = "product_attribute_value"
    __table_args__ = (UniqueConstraint("product_id", "key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    key: str
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    source: str = "seller"               # seller | ai_confirmed


class SpecSuggestion(SQLModel, table=True):
    """ค่าสเปกที่ AI เสนอจากคำอธิบายสินค้า — ผู้ขายต้องกดยืนยันเอง ไม่บันทึกเป็นสเปกอัตโนมัติ"""
    __tablename__ = "spec_suggestion"

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    key: str
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    status: str = "pending"              # pending | confirmed | dismissed
    created_at: datetime = Field(default_factory=utcnow)


class ShopShipping(SQLModel, table=True):
    """ค่าส่งของร้าน: เรทเดียวทั้งประเทศ + ส่งฟรีเมื่อซื้อครบ (ร้านที่ยังไม่ตั้ง = ค่าเริ่มต้น 40/500)"""
    __tablename__ = "shop_shipping"

    shop_id: int = Field(foreign_key="shop.id", primary_key=True)
    flat_rate: int = 40
    # None = ไม่มีส่งฟรีตามยอด (ค่าเริ่มต้น 500 ใส่ในโค้ด ไม่ใช่ default ของคอลัมน์
    # เพราะ SQLAlchemy จะแทน None ด้วย default ตอน INSERT ทำให้ตั้ง "ไม่มีส่งฟรี" ไม่ได้)
    free_over: Optional[int] = None
    days_min: int = 2
    days_max: int = 4


class ShopShippingRegion(SQLModel, table=True):
    """ค่าส่งเฉพาะภาค (ถ้าไม่ตั้ง ใช้ flat_rate ของร้าน)"""
    __tablename__ = "shop_shipping_region"
    __table_args__ = (UniqueConstraint("shop_id", "region"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    shop_id: int = Field(foreign_key="shop.id", index=True)
    region: str
    rate: int
    days_min: int = 2
    days_max: int = 4


class CompareList(SQLModel, table=True):
    """ถาดเปรียบเทียบที่บันทึกไว้ในบัญชี (สูงสุด 4 ชิ้น)"""
    __tablename__ = "compare_list"

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    ids_json: str = "[]"
    updated_at: datetime = Field(default_factory=utcnow)


class CompareSummary(SQLModel, table=True):
    """สรุป 1 บรรทัดต่อชุดสินค้า (+จังหวัด) — สร้างใหม่เมื่อ fingerprint ของข้อมูลที่ใช้เปลี่ยน"""
    __tablename__ = "compare_summary"

    sku_set_hash: str = Field(primary_key=True)
    fingerprint: str
    summary: str
    source: Optional[str] = None     # ai | rule (เฟส 4)
    created_at: datetime = Field(default_factory=utcnow)


# ---------- เฟส 3: แชทช่วยช้อป ----------

class AppSetting(SQLModel, table=True):
    """ค่าตั้งค่าที่เปลี่ยนได้โดยไม่ต้อง deploy (เช่น สวิตช์ปิดแชท) — ทับค่าจาก env"""
    __tablename__ = "app_setting"

    key: str = Field(primary_key=True)
    value: str
    updated_at: datetime = Field(default_factory=utcnow)


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_session"

    id: str = Field(primary_key=True)                 # uuid hex
    user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    client_key: str = Field(index=True)               # sha1(ip+device) — ไม่เก็บ IP ตรงๆ
    filters_json: str = "{}"                          # ตัวกรองที่สะสมจากบทสนทนา
    created_at: datetime = Field(default_factory=utcnow)


class ChatMessage(SQLModel, table=True):
    """log บทสนทนา (ตัดข้อมูลส่วนตัวแล้ว) เก็บ 30 วันเพื่อตรวจย้อนหลัง"""
    __tablename__ = "chat_message"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="chat_session.id", index=True)
    user_id: Optional[int] = Field(default=None, index=True)
    client_key: str = Field(index=True)
    role: str                                          # user | model
    text_masked: str
    intent: Optional[str] = None
    mode: Optional[str] = None                         # llm | canned | cache | fallback
    tool_calls: Optional[str] = None                   # JSON
    tokens_in: int = 0
    tokens_out: int = 0
    feedback: Optional[str] = None                     # up | down
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ChatCache(SQLModel, table=True):
    __tablename__ = "chat_cache"

    query_hash: str = Field(primary_key=True)
    response_json: str
    expires_at: datetime


# ---------- ดัชนี (index) ที่ PostgreSQL ไม่สร้างให้อัตโนมัติจาก foreign key ----------
# รายการเดียวใช้ทั้ง 2 ทาง: create_all (DB ใหม่ — ผ่าน Index ด้านล่าง) และ
# database.ensure_schema (DB เก่าบน Render — CREATE INDEX IF NOT EXISTS ชื่อเดียวกัน)
# ชื่อคงที่ ห้ามเปลี่ยน ไม่งั้นจะสร้างซ้ำ
# (ชื่อตาราง, ชื่อดัชนี, [คอลัมน์...])
EXTRA_INDEXES = [
    ("product", "ix_product_shop_id", ["shop_id"]),
    ("product", "ix_product_category_id", ["category_id"]),
    ("product", "ix_product_is_active_category_id", ["is_active", "category_id"]),
    ("productmedia", "ix_productmedia_product_id", ["product_id"]),
    ("cart", "ix_cart_user_id", ["user_id"]),
    ("cartitem", "ix_cartitem_cart_id", ["cart_id"]),
    ("cartitem", "ix_cartitem_product_id", ["product_id"]),
    ("orderitem", "ix_orderitem_order_id", ["order_id"]),
    ("orderitem", "ix_orderitem_product_id", ["product_id"]),
]

for _table, _name, _cols in EXTRA_INDEXES:
    _t = SQLModel.metadata.tables[_table]
    Index(_name, *[_t.c[c] for c in _cols])



# ---------- เฟส 4 ----------

class ReviewSummary(SQLModel, table=True):
    """สรุป "ลูกค้าชม / ลูกค้าติ" ต่อสินค้า — สร้างใหม่เมื่อรีวิวเปลี่ยน (fingerprint ไม่ตรง)"""
    __tablename__ = "review_summary"

    product_id: int = Field(foreign_key="product.id", primary_key=True)
    fingerprint: str
    praise_json: str = "[]"          # [{"text","quote"}] ที่ผ่านการตรวจแล้ว
    complaints_json: str = "[]"
    created_at: datetime = Field(default_factory=utcnow)


class ProductEmbedding(SQLModel, table=True):
    """เวกเตอร์ความหมายของข้อความสินค้า (เฉพาะข้อมูลสินค้า ไม่มีข้อมูลผู้ใช้) — ค้นหาตามความหมาย"""
    __tablename__ = "product_embedding"

    product_id: int = Field(foreign_key="product.id", primary_key=True)
    model: str
    vector_json: str
    text_hash: str
    updated_at: datetime = Field(default_factory=utcnow)
