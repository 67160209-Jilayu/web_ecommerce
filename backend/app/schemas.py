"""รูปแบบข้อมูลรับ-ส่งผ่าน API (แยกจาก models.py ที่เป็นโครงสร้างตารางจริง)"""
from datetime import date, datetime, timezone
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


class AttributeValueIn(SQLModel):
    key: str
    value_num: Optional[float] = None
    value_text: Optional[str] = None


class AttributeValueRead(SQLModel):
    key: str
    name_th: str
    unit: Optional[str] = None
    group_name: str
    data_type: str
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    display: Optional[str] = None
    source: str


class AttributeTemplateRead(SQLModel):
    key: str
    name_th: str
    unit: Optional[str] = None
    data_type: str
    options: Optional[list[str]] = None
    group_name: str
    better: str
    required: bool
    sort: int
    badge_label: Optional[str] = None


class ProductCreate(SQLModel):
    name: str
    price: int
    # รับไว้เพื่อไม่ให้ client เก่าพัง แต่ไม่ถูกใช้แล้ว — ราคาก่อนลดระบบคำนวณเอง
    original_price: Optional[int] = None
    category_id: Optional[int] = None
    description: str = ""
    stock: int = 0
    free_shipping: bool = False
    image: str = "📦"
    media: list[MediaItem] = []
    brand: Optional[str] = None
    model_code: Optional[str] = None
    barcode: Optional[str] = None
    attributes: list[AttributeValueIn] = []

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
    original_price: Optional[int] = None   # ไม่ถูกใช้แล้ว (ดู ProductCreate)
    category_id: Optional[int] = None
    description: Optional[str] = None
    stock: Optional[int] = None
    free_shipping: Optional[bool] = None
    image: Optional[str] = None
    media: Optional[list[MediaItem]] = None
    brand: Optional[str] = None
    model_code: Optional[str] = None
    barcode: Optional[str] = None
    attributes: Optional[list[AttributeValueIn]] = None   # ส่งมา = แทนทั้งชุด, ไม่ส่ง = คงเดิม


class ProductRead(SQLModel):
    """คงชื่อ field เดิมจากสัปดาห์ 1-4 ไว้ (shop_name แบบ flatten) เพื่อไม่ให้ frontend เดิมพัง
    แล้วเพิ่ม field ใหม่ต่อท้าย
    """

    id: int
    name: str
    price: int
    # ราคาก่อนลด (ราคาขีดฆ่า) ที่ระบบคำนวณ = ราคาต่ำสุดใน 30 วันก่อนราคาปัจจุบันเริ่มใช้
    # null = ไม่ได้ลดราคา ไม่ต้องแสดงราคาขีดฆ่า
    original_price: Optional[int] = None
    # % ส่วนลด — null = ไม่ต้องแสดง % (ไม่ได้ลด หรือถูกซ่อนเพราะขึ้นราคาก่อนลด)
    discount_percent: Optional[int] = None
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
    brand: Optional[str] = None
    model_code: Optional[str] = None
    barcode: Optional[str] = None
    attributes: list[AttributeValueRead] = []
    spec_complete: bool = False   # กรอกสเปกที่จำเป็นครบ → ป้าย "ข้อมูลครบ"
    match: Optional[str] = None   # เฉพาะผลค้นหา: keyword | semantic (เฟส 4)


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
    cart_item_id: Optional[int] = None
    price_at_add: Optional[int] = None   # ราคาตอนใส่ตะกร้า


class NoticeRead(SQLModel):
    """notice ราคาลดของสินค้าในตะกร้า (sku_id = product_id ในระบบนี้)"""
    id: int
    sku_id: int
    product_id: int
    cart_item_id: int
    product_name: str
    image: str = "📦"
    cover_url: Optional[str] = None
    old_price: int     # ราคาตอนใส่ตะกร้า
    new_price: int     # ราคาปัจจุบัน
    created_at: datetime
    read_at: Optional[datetime] = None


    @field_validator("created_at", "read_at")
    @classmethod
    def as_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        # DB เก็บเป็น UTC แบบ naive → ใส่ timezone ให้ JSON ออกเป็น ...+00:00 (JS แปลงเวลาไทยถูก)
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v


class NoticeList(SQLModel):
    unread_count: int
    notices: list[NoticeRead]


class NoticeMarkRead(SQLModel):
    ids: Optional[list[int]] = None   # None/ไม่ส่ง = ทุกอันที่ยังไม่อ่าน


class CartRead(SQLModel):
    token: str
    items: list[CartItemRead]
    total: int
    # notice ที่ยังไม่อ่าน (เฉพาะเจ้าของตะกร้าที่ล็อกอินอยู่ — guest ได้ [] เสมอ)
    notices: list[NoticeRead] = []


# ---------- Order ----------

class CheckoutRequest(SQLModel):
    recipient_name: str
    recipient_phone: str
    address: str
    note: str = ""
    payment_method: str = PaymentMethod.COD
    province: Optional[str] = None   # จังหวัดปลายทาง (ไม่ส่ง = เดาจากที่อยู่ / ใช้เรทเดียวทั้งประเทศ)

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


# ---------- Seller price dashboard ----------

class PriceWarning(SQLModel):
    code: str       # raise_before_discount | raise_before_discount_grace | recent_raise
    message: str    # ข้อความภาษาไทยอธิบายเหตุผลให้ผู้ขาย


class PriceStatusItem(SQLModel):
    product_id: int
    name: str
    is_active: bool
    price: int
    in_stock: bool
    ref_price: Optional[int] = None            # ราคาขีดฆ่าที่ผู้ซื้อเห็น (= ProductRead.original_price)
    min_30d: Optional[int] = None              # ราคาต่ำสุด 30 วันก่อนราคาปัจจุบันเริ่มใช้
    discount_percent: Optional[int] = None     # % ที่คำนวณได้ (แม้ถูกซ่อน)
    discount_hidden: bool = False              # true = ผู้ซื้อไม่เห็น %
    max_increase_14d_percent: Optional[float] = None
    warnings: list[PriceWarning] = []
    carts_holding: int = 0                     # จำนวนตะกร้าที่มีสินค้านี้ (ไม่ระบุตัวผู้ซื้อ)
    carts_notice_eligible: int = 0             # ในนั้นเป็นตะกร้าของผู้ใช้ที่ล็อกอิน (จะได้ notice ถ้าลดราคา)
    ref_updated_at: Optional[datetime] = None

    @field_validator("ref_updated_at")
    @classmethod
    def as_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v


class GraceInfo(SQLModel):
    enabled: bool
    active: bool
    starts_at: date
    ends_at: Optional[date] = None


class PriceRules(SQLModel):
    ref_window_days: int
    raise_window_days: int
    raise_percent: float
    notice_min_percent: float
    notice_min_baht: int


class PriceStatus(SQLModel):
    grace: GraceInfo
    rules: PriceRules
    items: list[PriceStatusItem]


# ---------- เฟส 2: AI เสนอสเปก / ค่าส่ง / เปรียบเทียบ ----------

class SpecSuggestionRead(SQLModel):
    id: int
    key: str
    name_th: str
    unit: Optional[str] = None
    value_num: Optional[float] = None
    value_text: Optional[str] = None
    display: Optional[str] = None


class KeysIn(SQLModel):
    keys: list[str]


class ProvinceRead(SQLModel):
    name: str
    region: str


class AccountProvince(SQLModel):
    province: Optional[str] = None
    region: Optional[str] = None
    source: Optional[str] = None   # account | order | null


class ProvinceIn(SQLModel):
    province: Optional[str] = None   # null = ล้างค่า


class RegionRate(SQLModel):
    region: str
    rate: int
    days_min: int = 2
    days_max: int = 4


class ShippingSettings(SQLModel):
    flat_rate: int = 40
    free_over: Optional[int] = 500
    days_min: int = 2
    days_max: int = 4
    region_rates: list[RegionRate] = []


class ShopQuote(SQLModel):
    shop_id: Optional[int] = None
    shop_name: str = ""
    subtotal: int
    fee: int
    days_min: int
    days_max: int
    free_reason: Optional[str] = None   # item | threshold | null
    free_over: Optional[int] = None


class ShippingQuote(SQLModel):
    province: Optional[str] = None
    region: Optional[str] = None
    shops: list[ShopQuote]
    shipping_total: int
    grand_total: int


class CompareShipping(SQLModel):
    fee: int
    days_min: int
    days_max: int
    free_reason: Optional[str] = None   # item = สินค้านี้ส่งฟรี | threshold = ซื้อครบ free_over | null
    free_over: Optional[int] = None


class CompareItem(SQLModel):
    product_id: int
    name: str
    image: str
    cover_url: Optional[str] = None
    price: int
    original_price: Optional[int] = None
    discount_percent: Optional[int] = None
    rating: float
    review_count: int
    shop_id: Optional[int] = None
    shop_name: str
    shop_rating: float
    stock: int
    spec_complete: bool
    category_id: Optional[int] = None
    shipping: CompareShipping
    total: int
    badges: list[str] = []


class CompareCell(SQLModel):
    display: Optional[str] = None   # null = "ร้านไม่ได้ระบุ"
    is_best: bool = False


class CompareRow(SQLModel):
    key: str
    name_th: str
    unit: Optional[str] = None
    better: str
    differs: bool
    cells: list[CompareCell]


class CompareGroup(SQLModel):
    name: str
    rows: list[CompareRow]


class CompareResult(SQLModel):
    province: Optional[str] = None
    region: Optional[str] = None
    same_category: bool
    summary: Optional[str] = None
    summary_source: Optional[str] = None   # ai | rule | fixed
    missing_ids: list[int] = []
    items: list[CompareItem]
    groups: list[CompareGroup]


class SameModelRow(SQLModel):
    product_id: int
    shop_id: Optional[int] = None
    shop_name: str
    shop_rating: float
    price: int
    shipping_fee: int
    total: int
    days_min: int
    days_max: int
    match: str   # barcode | brand_model
    free_reason: Optional[str] = None
    free_over: Optional[int] = None


class CompareIds(SQLModel):
    ids: list[int]


class Features(SQLModel):
    """สวิตช์ฟีเจอร์ที่ frontend ใช้ตัดสินใจว่าจะแสดงปุ่ม/ทางเข้าไหม (public, cache ได้)"""
    spec_suggest: bool          # มี LLM ให้ช่วยเสนอสเปก
    llm_provider: str           # gemini | fake | none
    chat: bool = False
    chat_rollout_percent: int = 0
    semantic_search: bool = False



# ---------- เฟส 4 ----------

class MaybeSameRow(SQLModel):
    product_id: int
    name: str
    image: str
    cover_url: Optional[str] = None
    shop_id: Optional[int] = None
    shop_name: str
    shop_rating: float
    price: int
    shipping_fee: int
    total: int
    days_min: int
    days_max: int
    free_reason: Optional[str] = None
    free_over: Optional[int] = None
    score: float
    reasons: list[str] = []
    label: str


class ReviewSummaryRead(SQLModel):
    available: bool
    review_count: int
    min_reviews: int
    label: Optional[str] = None
    praise: list[str] = []
    complaints: list[str] = []
    praise_quotes: list[str] = []
    complaint_quotes: list[str] = []
    summary: Optional[str] = None
    source: Optional[str] = None
    generated_at: Optional[datetime] = None

    @field_validator("generated_at")
    @classmethod
    def as_utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return v.replace(tzinfo=timezone.utc) if v is not None and v.tzinfo is None else v
