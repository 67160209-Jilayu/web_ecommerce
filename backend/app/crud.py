"""ฟังก์ชันอ่าน/เขียนข้อมูลจริงกับฐานข้อมูล

รวม business logic ทั้งหมดไว้ที่นี่ ให้ router ทำหน้าที่แค่รับ-ส่ง HTTP และแปลง error
เป็น status code เท่านั้น
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import object_session
from sqlmodel import Session, select

from app import models, pricing, schemas, semantic, shipping, specs
from app.auth import hash_password, verify_password
from app.models import OrderStatus, PaymentMethod, PriceSource
from app.storage import delete_files

# ค่าส่งย้ายไปอยู่ใน app/shipping.py (เรทต่อร้าน/ภาค) ตั้งแต่เฟส 2 — ค่าเริ่มต้นยังเป็น 40 / ส่งฟรีเมื่อครบ 500
SPEC_BOOST_POSITIONS = 3    # สินค้า "ข้อมูลครบ" ขยับขึ้นกี่อันดับในการเรียงค่าเริ่มต้น


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =====================================================================
# User / Auth
# =====================================================================

def create_user(session: Session, data: schemas.UserCreate) -> models.User:
    existing = session.exec(select(models.User).where(models.User.email == data.email)).first()
    if existing is not None:
        raise ValueError("อีเมลนี้ถูกใช้สมัครไปแล้ว")

    user = models.User(
        email=data.email,
        name=data.name,
        hashed_password=hash_password(data.password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> Optional[models.User]:
    user = session.exec(select(models.User).where(models.User.email == email)).first()
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return user


# =====================================================================
# Category
# =====================================================================

def list_categories(session: Session) -> List[models.Category]:
    return session.exec(select(models.Category).order_by(models.Category.id)).all()


# =====================================================================
# Shop
# =====================================================================

def _to_shop_read(session: Session, shop: models.Shop) -> schemas.ShopRead:
    product_count = len(
        session.exec(
            select(models.Product).where(
                models.Product.shop_id == shop.id,
                models.Product.is_active == True,  # noqa: E712
            )
        ).all()
    )
    return schemas.ShopRead(
        id=shop.id,
        name=shop.name,
        description=shop.description,
        rating=round(shop.rating, 2),
        review_count=shop.review_count,
        is_verified=shop.is_verified,
        product_count=product_count,
    )


def get_shop_by_owner(session: Session, user_id: int) -> Optional[models.Shop]:
    return session.exec(select(models.Shop).where(models.Shop.owner_id == user_id)).first()


def get_shop(session: Session, shop_id: int) -> Optional[models.Shop]:
    return session.get(models.Shop, shop_id)


def create_shop(session: Session, owner: models.User, data: schemas.ShopCreate) -> models.Shop:
    if get_shop_by_owner(session, owner.id) is not None:
        raise ValueError("คุณมีร้านค้าอยู่แล้ว 1 บัญชีเปิดได้ 1 ร้าน")
    if not data.name.strip():
        raise ValueError("กรุณาตั้งชื่อร้าน")

    shop = models.Shop(owner_id=owner.id, name=data.name.strip(), description=data.description)
    session.add(shop)
    session.commit()
    session.refresh(shop)
    return shop


def update_shop(session: Session, shop: models.Shop, data: schemas.ShopUpdate) -> models.Shop:
    if data.name is not None:
        if not data.name.strip():
            raise ValueError("ชื่อร้านห้ามว่าง")
        shop.name = data.name.strip()
    if data.description is not None:
        shop.description = data.description
    session.add(shop)
    session.commit()
    session.refresh(shop)
    return shop


def list_shops(session: Session) -> List[schemas.ShopRead]:
    shops = session.exec(select(models.Shop)).all()
    return [_to_shop_read(session, s) for s in shops]


# =====================================================================
# Product
# =====================================================================

def _to_product_read(product: models.Product) -> schemas.ProductRead:
    # ราคาก่อนลดคำนวณโดยระบบเท่านั้น (ค่า original_price ที่ผู้ขายเคยพิมพ์ไว้ในตารางไม่ถูกใช้แล้ว)
    display = pricing.compute_display(product)
    return schemas.ProductRead(
        id=product.id,
        name=product.name,
        price=product.price,
        original_price=display.ref_price,
        discount_percent=display.shown_percent,
        image=product.image,
        cover_url=product.cover_url,
        shop_id=product.shop_id,
        shop_name=product.shop.name if product.shop else "ไม่ระบุร้าน",
        rating=round(product.rating, 2),
        review_count=product.review_count,
        sold=product.sold,
        stock=product.stock,
        free_shipping=product.free_shipping,
        category=product.category.name if product.category else "ทั่วไป",
        category_id=product.category_id,
        description=product.description,
        is_active=product.is_active,
        media=[schemas.MediaItem(url=m.url, media_type=m.media_type) for m in product.media],
        brand=product.brand,
        model_code=product.model_code,
        barcode=product.barcode,
        **_spec_fields(product),
    )


def _spec_fields(product: models.Product) -> dict:
    session = object_session(product)
    if session is None or product.id is None:
        return {}
    values = specs.values_of(session, product.id)
    return {
        "attributes": specs.attribute_reads(session, product),
        "spec_complete": specs.is_complete(session, product, values),
    }


def _clean_code(value: Optional[str]) -> Optional[str]:
    value = (value or "").strip()
    return value[:100] or None


def list_products(
    session: Session,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    shop_id: Optional[int] = None,
    sort: str = "latest",
) -> List[schemas.ProductRead]:
    """คืนสินค้าที่ยังเปิดขาย พร้อมตัวกรอง/เรียงลำดับ"""
    stmt = select(models.Product).where(models.Product.is_active == True)  # noqa: E712

    if category_id is not None:
        stmt = stmt.where(models.Product.category_id == category_id)
    if min_price is not None:
        stmt = stmt.where(models.Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(models.Product.price <= max_price)
    if shop_id is not None:
        stmt = stmt.where(models.Product.shop_id == shop_id)

    if sort == "price_asc":
        stmt = stmt.order_by(models.Product.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(models.Product.price.desc())
    elif sort == "popular":
        stmt = stmt.order_by(models.Product.sold.desc())
    elif sort == "rating":
        stmt = stmt.order_by(models.Product.rating.desc())
    else:  # latest
        stmt = stmt.order_by(models.Product.id.desc())

    products = session.exec(stmt).all()
    filtered = list(products)   # ผ่านตัวกรองหมวด/ราคา/ร้านแล้ว (ใช้เป็นขอบเขตของการค้นตามความหมาย)

    # ค้นหาด้วยคำ ทำในหน่วยความจำเพื่อให้รองรับภาษาไทยแบบไม่สนตัวพิมพ์เล็ก-ใหญ่
    if search:
        keyword = search.strip().lower()
        products = [
            p for p in products
            if keyword in p.name.lower() or keyword in (p.description or "").lower()
        ]

    reads = [_to_product_read(p) for p in products]
    if search:
        for r in reads:
            r.match = "keyword"
    if sort not in ("price_asc", "price_desc", "popular", "rating"):
        # เฟส 2: สินค้าที่กรอกสเปกครบได้อันดับดีขึ้นเล็กน้อย (ขยับขึ้น SPEC_BOOST_POSITIONS ตำแหน่ง)
        # เฉพาะการเรียงค่าเริ่มต้น — ถ้าผู้ใช้เลือกเรียงตามราคา/ยอดขาย/คะแนนเอง ไม่ยุ่ง
        reads = [
            r for _, r in sorted(
                enumerate(reads),
                key=lambda ir: (ir[0] - (SPEC_BOOST_POSITIONS + 0.5 if ir[1].spec_complete else 0), ir[0]),
            )
        ]
    if search:
        # เฟส 4: ต่อท้ายด้วยสินค้าที่ความหมายใกล้คำค้น (ผลค้นด้วยคำยังอยู่ครบและลำดับเดิม)
        # ปิดสวิตช์/ไม่มีผู้ให้บริการ/ผิดพลาด → semantic_ids คืน [] = ผลค้นหาเดิม
        by_id = {p.id: p for p in filtered}
        for pid in semantic.semantic_ids(session, search, filtered, exclude={p.id for p in products}):
            r = _to_product_read(by_id[pid])
            r.match = "semantic"
            reads.append(r)
    return reads


def list_products_by_shop_owner(session: Session, shop_id: int) -> List[schemas.ProductRead]:
    """สินค้าทั้งหมดในร้าน รวมที่ปิดขายแล้ว (สำหรับเจ้าของร้านดูในแดชบอร์ด)"""
    products = session.exec(
        select(models.Product)
        .where(models.Product.shop_id == shop_id)
        .order_by(models.Product.id.desc())
    ).all()
    return [_to_product_read(p) for p in products]


def get_product(session: Session, product_id: int) -> Optional[schemas.ProductRead]:
    product = session.get(models.Product, product_id)
    return _to_product_read(product) if product else None


def _delete_unreferenced_files(session: Session, urls: set) -> None:
    """ลบไฟล์บนดิสก์เฉพาะ URL ที่ไม่มีสินค้าชิ้นไหนอ้างอิงอยู่แล้ว

    ต้องเช็คก่อนลบ เพราะผู้ขายอาจใช้ไฟล์เดียวกันกับสินค้าหลายชิ้น
    (frontend ส่ง URL เดิมกลับมาได้ถ้า copy มาจากสินค้าอื่น)
    """
    if not urls:
        return

    still_used = {
        m.url
        for m in session.exec(
            select(models.ProductMedia).where(models.ProductMedia.url.in_(urls))
        ).all()
    }
    delete_files(urls - still_used)


def _replace_media(session: Session, product: models.Product, media: list) -> None:
    """ลบสื่อเดิมทั้งหมดแล้วใส่ชุดใหม่ (ง่ายและถูกต้องกว่าการ diff ทีละรายการ)

    สื่อที่ถูกเอาออกและไม่มีสินค้าอื่นใช้แล้ว จะถูกลบไฟล์ทิ้งด้วย ไม่ปล่อยค้างกินพื้นที่
    """
    removed_urls = {m.url for m in product.media} - {item.url for item in media}

    # ต้องตัดออกจาก relationship ด้วย ไม่ใช่แค่ session.delete()
    # ถ้าตัดไม่ครบ collection จะยังถือ object ที่ถูกลบไปแล้วไว้ในหน่วยความจำ
    # แล้ว session.add(product) ทีหลังจะ cascade ไปโดนมันจน error
    for old in list(product.media):
        product.media.remove(old)
        session.delete(old)
    session.flush()

    # เพิ่มผ่าน relationship เพื่อให้ collection ในหน่วยความจำตรงกับฐานข้อมูลเสมอ
    for i, item in enumerate(media):
        product.media.append(
            models.ProductMedia(
                url=item.url,
                media_type=item.media_type,
                sort_order=i,
            )
        )
    product.cover_url = media[0].url if media and media[0].media_type == "image" else None
    if product.cover_url is None and media:
        # ถ้าสื่อชิ้นแรกเป็นวิดีโอ ใช้รูปแรกที่เจอเป็นปกแทน
        first_image = next((m for m in media if m.media_type == "image"), None)
        product.cover_url = first_image.url if first_image else None

    session.flush()
    _delete_unreferenced_files(session, removed_urls)


def create_product(
    session: Session, shop: models.Shop, data: schemas.ProductCreate
) -> schemas.ProductRead:
    if data.category_id is not None and session.get(models.Category, data.category_id) is None:
        raise ValueError("ไม่พบหมวดหมู่ที่เลือก")
    clean_attrs = specs.validate_values(
        session, data.category_id, [a.model_dump() for a in data.attributes]
    )

    product = models.Product(
        shop_id=shop.id,
        category_id=data.category_id,
        name=data.name.strip(),
        price=data.price,
        # ไม่รับราคาขีดฆ่าจากผู้ขายแล้ว — ระบบคำนวณจากประวัติราคาเอง
        description=data.description,
        stock=data.stock,
        free_shipping=data.free_shipping,
        image=data.image or "📦",
        brand=_clean_code(data.brand),
        model_code=_clean_code(data.model_code),
        barcode=_clean_code(data.barcode),
    )
    session.add(product)
    session.flush()

    _replace_media(session, product, data.media)
    specs.replace_values(session, product, clean_attrs)
    pricing.record_price_state(session, product, PriceSource.SELLER)
    session.commit()
    pricing.after_price_change(session, [product.id])
    semantic.after_product_change(session, product.id)
    session.refresh(product)
    return _to_product_read(product)


def update_product(
    session: Session, product: models.Product, data: schemas.ProductUpdate
) -> schemas.ProductRead:
    if data.category_id is not None and session.get(models.Category, data.category_id) is None:
        raise ValueError("ไม่พบหมวดหมู่ที่เลือก")

    if data.name is not None:
        if not data.name.strip():
            raise ValueError("ชื่อสินค้าห้ามว่าง")
        product.name = data.name.strip()
    if data.price is not None:
        if data.price <= 0:
            raise ValueError("ราคาต้องมากกว่า 0")
        product.price = data.price
    # data.original_price ถูกละไว้โดยตั้งใจ: ผู้ขายตั้งราคาขีดฆ่าเองไม่ได้แล้ว
    if data.category_id is not None:
        product.category_id = data.category_id
    if data.description is not None:
        product.description = data.description
    if data.stock is not None:
        if data.stock < 0:
            raise ValueError("จำนวนสินค้าต้องไม่ติดลบ")
        product.stock = data.stock
    if data.free_shipping is not None:
        product.free_shipping = data.free_shipping
    if data.image is not None:
        product.image = data.image
    if data.media is not None:
        _replace_media(session, product, data.media)
    # สตริงว่าง = ล้างค่า, ไม่ส่ง (None) = คงเดิม
    if data.brand is not None:
        product.brand = _clean_code(data.brand)
    if data.model_code is not None:
        product.model_code = _clean_code(data.model_code)
    if data.barcode is not None:
        product.barcode = _clean_code(data.barcode)
    if data.attributes is not None:
        clean_attrs = specs.validate_values(
            session, product.category_id, [a.model_dump() for a in data.attributes]
        )
        specs.replace_values(session, product, clean_attrs)
    elif data.category_id is not None:
        specs.drop_values_not_in_template(session, product)

    session.add(product)
    # จดประวัติราคาใน transaction เดียวกับการแก้ราคา (จดเฉพาะเมื่อราคา/สถานะสต็อกเปลี่ยนจริง)
    changed = pricing.record_price_state(session, product, PriceSource.SELLER)
    session.commit()
    if changed is not None:
        pricing.after_price_change(session, [product.id])
    semantic.after_product_change(session, product.id)   # embed ใหม่เฉพาะเมื่อข้อความสินค้าเปลี่ยน
    session.refresh(product)
    return _to_product_read(product)


def deactivate_product(session: Session, product: models.Product) -> None:
    """ปิดขายแทนการลบจริง เพราะ OrderItem เก่ายังอ้างอิงสินค้านี้อยู่"""
    product.is_active = False
    session.add(product)
    session.commit()
    # สินค้าปิดขาย → notice ราคาลดของสินค้านี้ในตะกร้าทุกคนต้องหายไป
    pricing.after_price_change(session, [product.id])


# =====================================================================
# Cart
# =====================================================================

def _to_notice_read(
    notice: models.CartPriceNotice, product: Optional[models.Product]
) -> schemas.NoticeRead:
    return schemas.NoticeRead(
        id=notice.id,
        sku_id=notice.sku_id,
        product_id=notice.sku_id,
        cart_item_id=notice.cart_item_id,
        product_name=product.name if product else "",
        image=product.image if product else "📦",
        cover_url=product.cover_url if product else None,
        old_price=notice.old_price,
        new_price=notice.new_price,
        created_at=notice.created_at,
        read_at=notice.read_at,
    )


def list_notices(
    session: Session, user: models.User, include_read: bool = False
) -> List[schemas.NoticeRead]:
    """notice ราคาลดของสินค้าในตะกร้าผู้ใช้ (ค่าเริ่มต้น: เฉพาะที่ยังไม่อ่าน) ใหม่สุดก่อน"""
    stmt = select(models.CartPriceNotice).where(models.CartPriceNotice.user_id == user.id)
    if not include_read:
        stmt = stmt.where(models.CartPriceNotice.read_at == None)  # noqa: E711
    stmt = stmt.order_by(
        models.CartPriceNotice.created_at.desc(), models.CartPriceNotice.id.desc()
    )
    result = []
    for notice in session.exec(stmt).all():
        product = session.get(models.Product, notice.sku_id)
        item = session.get(models.CartItem, notice.cart_item_id)
        cart = item.cart if item else None
        # กันข้อมูลค้าง: สินค้าปิดขาย หรือ cart_item ไม่ได้อยู่ในตะกร้าของผู้ใช้นี้แล้ว → ไม่แสดง
        if product is None or not product.is_active or cart is None or cart.user_id != user.id:
            continue
        result.append(_to_notice_read(notice, product))
    return result


def mark_notices_read(
    session: Session, user: models.User, ids: Optional[List[int]] = None
) -> int:
    """ทำเครื่องหมายว่าอ่านแล้ว (ids=None = ทุกอันที่ยังไม่อ่าน) — แก้ได้เฉพาะ notice ของตัวเอง"""
    stmt = select(models.CartPriceNotice).where(
        models.CartPriceNotice.user_id == user.id,
        models.CartPriceNotice.read_at == None,  # noqa: E711
    )
    if ids is not None:
        if not ids:
            return 0
        stmt = stmt.where(models.CartPriceNotice.id.in_(ids))
    notices = session.exec(stmt).all()
    now = pricing.utcnow_naive()
    for notice in notices:
        notice.read_at = now
        session.add(notice)
    session.commit()
    return len(notices)


def _delete_cart_item(session: Session, item: models.CartItem) -> None:
    """ลบ cart_item พร้อม notice ของมัน (ต้องลบ notice ก่อนเพราะมี FK อ้างอยู่)"""
    pricing.delete_notice_for_item(session, item.id)
    session.delete(item)


def _to_cart_read(
    cart: models.Cart, viewer: Optional[models.User] = None
) -> schemas.CartRead:
    items = []
    total = 0
    notices: List[schemas.NoticeRead] = []
    session = object_session(cart)
    # notice แสดงเฉพาะเจ้าของตะกร้าที่ล็อกอินอยู่ (guest / คนอื่นที่ถือ token เดียวกันไม่เห็น)
    if viewer is not None and cart.user_id == viewer.id and session is not None:
        notices = list_notices(session, viewer)
    for item in cart.items:
        product = item.product
        if product is None or not product.is_active:
            continue  # สินค้าถูกลบ/ปิดขายไปแล้ว ไม่ต้องแสดงในตะกร้า
        total += product.price * item.quantity
        items.append(
            schemas.CartItemRead(
                product_id=item.product_id,
                name=product.name,
                price=product.price,
                image=product.image,
                cover_url=product.cover_url,
                stock=product.stock,
                quantity=item.quantity,
                free_shipping=product.free_shipping,
                shop_id=product.shop_id,
                shop_name=product.shop.name if product.shop else "",
                cart_item_id=item.id,
                price_at_add=item.price_at_add,
            )
        )
    return schemas.CartRead(token=cart.token, items=items, total=total, notices=notices)


def get_cart(
    session: Session, token: str, viewer: Optional[models.User] = None
) -> schemas.CartRead:
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    if cart is None:
        return schemas.CartRead(token=token, items=[], total=0)
    return _to_cart_read(cart, viewer)


def _get_or_create_cart(session: Session, token: str) -> models.Cart:
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    if cart:
        return cart
    cart = models.Cart(token=token)
    session.add(cart)
    session.commit()
    session.refresh(cart)
    return cart


def add_cart_item(
    session: Session, token: str, data: schemas.CartItemCreate, user: Optional[models.User] = None
) -> schemas.CartRead:
    # Edge Case (จากเอกสาร User Journey): "สินค้าหมดสต็อกระหว่างที่ลูกค้ากำลังเช็คเอาท์"
    # ล็อก row สินค้าไว้ระหว่าง transaction กันสองคำขอพร้อมกันอ่าน stock ค่าเดิม
    product = session.exec(
        select(models.Product).where(models.Product.id == data.product_id).with_for_update()
    ).first()
    if product is None or not product.is_active:
        raise ValueError("ไม่พบสินค้านี้")
    if product.stock <= 0:
        raise ValueError("สินค้าหมดสต็อกแล้ว")
    if user is not None and product.shop and product.shop.owner_id == user.id:
        raise ValueError("ไม่สามารถซื้อสินค้าของร้านตัวเองได้")

    cart = _get_or_create_cart(session, token)
    existing = session.exec(
        select(models.CartItem).where(
            models.CartItem.cart_id == cart.id,
            models.CartItem.product_id == data.product_id,
        )
    ).first()

    new_qty = min((existing.quantity if existing else 0) + data.quantity, product.stock)
    if existing:
        # คง price_at_add เดิมไว้ — notice เทียบกับราคาตอนใส่ตะกร้าครั้งแรก
        existing.quantity = new_qty
        if existing.price_at_add is None:
            existing.price_at_add = product.price
        session.add(existing)
    else:
        session.add(
            models.CartItem(
                cart_id=cart.id,
                product_id=data.product_id,
                quantity=new_qty,
                price_at_add=product.price,
            )
        )
    session.commit()
    session.refresh(cart)
    return _to_cart_read(cart, user)


def update_cart_item(
    session: Session,
    token: str,
    product_id: int,
    quantity: int,
    viewer: Optional[models.User] = None,
) -> schemas.CartRead:
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    if cart is None:
        raise ValueError("ไม่พบตะกร้านี้")

    item = session.exec(
        select(models.CartItem).where(
            models.CartItem.cart_id == cart.id,
            models.CartItem.product_id == product_id,
        )
    ).first()
    if item is None:
        raise ValueError("ไม่พบสินค้านี้ในตะกร้า")

    if quantity <= 0:
        _delete_cart_item(session, item)
    else:
        product = session.get(models.Product, product_id)
        item.quantity = min(quantity, product.stock) if product else quantity
        session.add(item)
    session.commit()
    session.refresh(cart)
    return _to_cart_read(cart, viewer)


def remove_cart_item(
    session: Session, token: str, product_id: int, viewer: Optional[models.User] = None
) -> schemas.CartRead:
    return update_cart_item(session, token, product_id, 0, viewer)


def merge_cart_to_user(session: Session, token: str, user: models.User) -> schemas.CartRead:
    """ผูกตะกร้า guest เข้ากับบัญชีตอนล็อกอิน — ถ้าบัญชีมีตะกร้าเดิมอยู่แล้ว จะรวมรายการเข้าด้วยกัน

    ความปลอดภัย: ถ้า token นี้เป็นของบัญชีอื่นอยู่แล้ว (เช่น ใช้เครื่องร่วมกันแล้วคนก่อนหน้า
    ลืมล้าง token) ห้าม claim เด็ดขาด — คืนตะกร้าของผู้ใช้ปัจจุบันแทน ไม่งั้นสินค้าในตะกร้า
    ของคนก่อนจะรั่วไปให้คนถัดไปเห็น
    """
    guest_cart = _get_or_create_cart(session, token)

    if guest_cart.user_id is not None and guest_cart.user_id != user.id:
        own_cart = session.exec(
            select(models.Cart).where(models.Cart.user_id == user.id)
        ).first()
        if own_cart is None:
            own_cart = models.Cart(user_id=user.id)
            session.add(own_cart)
            session.commit()
            session.refresh(own_cart)
        return _to_cart_read(own_cart, user)

    user_cart = session.exec(
        select(models.Cart).where(
            models.Cart.user_id == user.id, models.Cart.id != guest_cart.id
        )
    ).first()

    if user_cart is None:
        guest_cart.user_id = user.id
        session.add(guest_cart)
        session.commit()
        # ตะกร้าเพิ่งผูกบัญชี → ตรวจ notice ทันที (ราคาอาจลดไปแล้วระหว่างเป็น guest)
        pricing.sync_cart_notices(session, cart_id=guest_cart.id)
        session.commit()
        session.refresh(guest_cart)
        return _to_cart_read(guest_cart, user)

    # รวมรายการจากตะกร้า guest เข้าตะกร้าเดิมของผู้ใช้
    for item in list(guest_cart.items):
        existing = session.exec(
            select(models.CartItem).where(
                models.CartItem.cart_id == user_cart.id,
                models.CartItem.product_id == item.product_id,
            )
        ).first()
        product = session.get(models.Product, item.product_id)
        cap = product.stock if product else item.quantity
        if existing:
            existing.quantity = min(existing.quantity + item.quantity, cap)
            if existing.price_at_add is None:
                existing.price_at_add = item.price_at_add
            session.add(existing)
        else:
            session.add(
                models.CartItem(
                    cart_id=user_cart.id,
                    product_id=item.product_id,
                    quantity=min(item.quantity, cap),
                    price_at_add=item.price_at_add,
                )
            )
        _delete_cart_item(session, item)
    session.commit()
    pricing.sync_cart_notices(session, cart_id=user_cart.id)
    session.commit()
    session.refresh(user_cart)
    return _to_cart_read(user_cart, user)


def get_user_cart_token(session: Session, user: models.User) -> Optional[str]:
    cart = session.exec(select(models.Cart).where(models.Cart.user_id == user.id)).first()
    return cart.token if cart else None


# =====================================================================
# Order
# =====================================================================

def _generate_order_number() -> str:
    return f"SM{_now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def _to_order_read(order: models.Order) -> schemas.OrderRead:
    return schemas.OrderRead(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_method=order.payment_method,
        shop_id=order.shop_id,
        shop_name=order.shop.name if order.shop else "",
        buyer_name=order.buyer.name if order.buyer else "",
        subtotal=order.subtotal,
        shipping_fee=order.shipping_fee,
        total=order.total,
        recipient_name=order.recipient_name,
        recipient_phone=order.recipient_phone,
        address=order.address,
        note=order.note,
        created_at=order.created_at,
        items=[
            schemas.OrderItemRead(
                id=it.id,
                product_id=it.product_id,
                product_name=it.product_name,
                product_price=it.product_price,
                product_image=it.product_image,
                product_cover_url=it.product_cover_url,
                quantity=it.quantity,
                subtotal=it.subtotal,
                reviewed=it.review is not None,
            )
            for it in order.items
        ],
    )


def checkout(
    session: Session, token: str, user: models.User, data: schemas.CheckoutRequest
) -> List[schemas.OrderRead]:
    """แปลงตะกร้าเป็นออเดอร์ — แยก 1 ออเดอร์ต่อ 1 ร้าน เพราะแต่ละร้านจัดส่งแยกกัน

    ตัด stock ภายใน transaction เดียวโดยล็อก row สินค้าไว้ก่อน ถ้าสินค้าชิ้นใดชิ้นหนึ่งไม่พอ
    จะยกเลิกทั้งหมด (ไม่สร้างออเดอร์ค้างไว้ครึ่งๆ กลางๆ)
    """
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    if cart is None or not cart.items:
        raise ValueError("ตะกร้าว่าง ไม่สามารถสั่งซื้อได้")

    # จัดกลุ่มรายการตามร้าน + ล็อก row สินค้าทุกตัวก่อนตรวจ stock
    by_shop: dict[int, list] = {}
    skipped: list[str] = []

    for item in list(cart.items):
        product = session.exec(
            select(models.Product).where(models.Product.id == item.product_id).with_for_update()
        ).first()

        if product is None or not product.is_active:
            skipped.append(item.product.name if item.product else f"#{item.product_id}")
            _delete_cart_item(session, item)
            continue
        if product.shop and product.shop.owner_id == user.id:
            raise ValueError(f"ไม่สามารถซื้อสินค้าของร้านตัวเองได้: {product.name}")
        if product.stock < item.quantity:
            raise ValueError(
                f"สินค้า '{product.name}' เหลือเพียง {product.stock} ชิ้น "
                f"(ต้องการ {item.quantity} ชิ้น) กรุณาปรับจำนวนในตะกร้า"
            )
        by_shop.setdefault(product.shop_id, []).append((product, item.quantity))

    if not by_shop:
        session.commit()
        raise ValueError("ไม่มีสินค้าที่สั่งซื้อได้ในตะกร้า (สินค้าอาจถูกปิดขายไปแล้ว)")

    created: List[models.Order] = []
    changed_ids: List[int] = []
    province = shipping.normalize_province(data.province) or shipping.detect_province(data.address)
    if data.province and province is None:
        raise ValueError("จังหวัดไม่ถูกต้อง")
    for shop_id, entries in by_shop.items():
        # ใช้ engine ค่าส่งเดียวกับหน้าเทียบ/ใบเสนอค่าส่ง ราคาที่เห็นจึงตรงกับที่จ่ายจริง
        q = shipping.quote(session, shop_id, entries, province)
        subtotal, shipping_fee = q["subtotal"], q["fee"]

        # COD ถือว่ายืนยันคำสั่งซื้อได้เลย ส่วนโอน/บัตรต้องกดชำระก่อน
        is_cod = data.payment_method == PaymentMethod.COD
        order = models.Order(
            order_number=_generate_order_number(),
            buyer_id=user.id,
            shop_id=shop_id,
            status=OrderStatus.PAID if is_cod else OrderStatus.PENDING_PAYMENT,
            payment_method=data.payment_method,
            subtotal=subtotal,
            shipping_fee=shipping_fee,
            total=subtotal + shipping_fee,
            recipient_name=data.recipient_name,
            recipient_phone=data.recipient_phone,
            address=data.address,
            note=data.note,
            province=province,
            paid_at=_now() if is_cod else None,
        )
        session.add(order)
        session.flush()

        for product, qty in entries:
            session.add(
                models.OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    product_price=product.price,
                    product_image=product.image,
                    product_cover_url=product.cover_url,
                    quantity=qty,
                    subtotal=product.price * qty,
                )
            )
            product.stock -= qty
            if is_cod:
                product.sold += qty
            session.add(product)
            # สต็อกหมดจาก checkout = สถานะมีของเปลี่ยน → จดประวัติใน transaction เดียวกัน
            if pricing.record_price_state(session, product, PriceSource.SYSTEM) is not None:
                changed_ids.append(product.id)

        created.append(order)

    # เคลียร์ตะกร้าหลังสร้างออเดอร์สำเร็จ (notice ของรายการเหล่านี้หายไปด้วย)
    for item in list(cart.items):
        _delete_cart_item(session, item)

    session.commit()
    if changed_ids:
        pricing.after_price_change(session, changed_ids)
    for order in created:
        session.refresh(order)
    return [_to_order_read(o) for o in created]


def list_orders_buying(session: Session, user: models.User) -> List[schemas.OrderRead]:
    orders = session.exec(
        select(models.Order)
        .where(models.Order.buyer_id == user.id)
        .order_by(models.Order.id.desc())
    ).all()
    return [_to_order_read(o) for o in orders]


def list_orders_selling(session: Session, shop: models.Shop) -> List[schemas.OrderRead]:
    orders = session.exec(
        select(models.Order)
        .where(models.Order.shop_id == shop.id)
        .order_by(models.Order.id.desc())
    ).all()
    return [_to_order_read(o) for o in orders]


def get_order_for_user(
    session: Session, order_id: int, user: models.User
) -> schemas.OrderRead:
    """คืนออเดอร์เฉพาะเมื่อผู้เรียกเป็นผู้ซื้อหรือเจ้าของร้านเท่านั้น"""
    order = session.get(models.Order, order_id)
    if order is None:
        raise LookupError("ไม่พบคำสั่งซื้อนี้")
    is_buyer = order.buyer_id == user.id
    is_seller = order.shop is not None and order.shop.owner_id == user.id
    if not (is_buyer or is_seller):
        raise PermissionError("คุณไม่มีสิทธิ์ดูคำสั่งซื้อนี้")
    return _to_order_read(order)


def _load_order_for_action(
    session: Session, order_id: int, user: models.User, *, as_seller: bool
) -> models.Order:
    order = session.get(models.Order, order_id)
    if order is None:
        raise LookupError("ไม่พบคำสั่งซื้อนี้")
    if as_seller:
        if order.shop is None or order.shop.owner_id != user.id:
            raise PermissionError("เฉพาะร้านค้าเจ้าของคำสั่งซื้อเท่านั้นที่ทำรายการนี้ได้")
    else:
        if order.buyer_id != user.id:
            raise PermissionError("เฉพาะผู้สั่งซื้อเท่านั้นที่ทำรายการนี้ได้")
    return order


def pay_order(session: Session, order_id: int, user: models.User) -> schemas.OrderRead:
    order = _load_order_for_action(session, order_id, user, as_seller=False)
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise ValueError("คำสั่งซื้อนี้ไม่ได้อยู่ในสถานะรอชำระเงิน")

    order.status = OrderStatus.PAID
    order.paid_at = _now()
    for item in order.items:
        product = session.get(models.Product, item.product_id)
        if product:
            product.sold += item.quantity
            session.add(product)
    session.add(order)
    session.commit()
    session.refresh(order)
    return _to_order_read(order)


def ship_order(session: Session, order_id: int, user: models.User) -> schemas.OrderRead:
    order = _load_order_for_action(session, order_id, user, as_seller=True)
    if order.status != OrderStatus.PAID:
        raise ValueError("จัดส่งได้เฉพาะคำสั่งซื้อที่ชำระเงินแล้ว")

    order.status = OrderStatus.SHIPPED
    order.shipped_at = _now()
    session.add(order)
    session.commit()
    session.refresh(order)
    return _to_order_read(order)


def receive_order(session: Session, order_id: int, user: models.User) -> schemas.OrderRead:
    order = _load_order_for_action(session, order_id, user, as_seller=False)
    if order.status != OrderStatus.SHIPPED:
        raise ValueError("กดรับสินค้าได้เฉพาะคำสั่งซื้อที่จัดส่งแล้ว")

    order.status = OrderStatus.DELIVERED
    order.delivered_at = _now()
    session.add(order)
    session.commit()
    session.refresh(order)
    return _to_order_read(order)


def cancel_order(session: Session, order_id: int, user: models.User) -> schemas.OrderRead:
    """ยกเลิกได้ทั้งผู้ซื้อและร้านค้า ตราบใดที่ยังไม่จัดส่ง — คืน stock ให้อัตโนมัติ"""
    order = session.get(models.Order, order_id)
    if order is None:
        raise LookupError("ไม่พบคำสั่งซื้อนี้")

    is_buyer = order.buyer_id == user.id
    is_seller = order.shop is not None and order.shop.owner_id == user.id
    if not (is_buyer or is_seller):
        raise PermissionError("คุณไม่มีสิทธิ์ยกเลิกคำสั่งซื้อนี้")

    if order.status not in (OrderStatus.PENDING_PAYMENT, OrderStatus.PAID):
        raise ValueError("ยกเลิกได้เฉพาะคำสั่งซื้อที่ยังไม่จัดส่งเท่านั้น")

    was_paid = order.status == OrderStatus.PAID
    changed_ids: List[int] = []
    for item in order.items:
        product = session.exec(
            select(models.Product).where(models.Product.id == item.product_id).with_for_update()
        ).first()
        if product:
            product.stock += item.quantity           # คืน stock
            if was_paid:
                product.sold = max(0, product.sold - item.quantity)
            session.add(product)
            if pricing.record_price_state(session, product, PriceSource.SYSTEM) is not None:
                changed_ids.append(product.id)

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = _now()
    session.add(order)
    session.commit()
    if changed_ids:
        pricing.after_price_change(session, changed_ids)
    session.refresh(order)
    return _to_order_read(order)


# =====================================================================
# Review
# =====================================================================

def _recalculate_ratings(session: Session, product_id: int, shop_id: int) -> None:
    """คำนวณคะแนนเฉลี่ยของสินค้าและร้านใหม่จากรีวิวจริงทั้งหมด"""
    product_reviews = session.exec(
        select(models.Review).where(models.Review.product_id == product_id)
    ).all()
    product = session.get(models.Product, product_id)
    if product:
        product.review_count = len(product_reviews)
        product.rating = (
            sum(r.rating for r in product_reviews) / len(product_reviews)
            if product_reviews else 0.0
        )
        session.add(product)

    shop_reviews = session.exec(
        select(models.Review).where(models.Review.shop_id == shop_id)
    ).all()
    shop = session.get(models.Shop, shop_id)
    if shop:
        shop.review_count = len(shop_reviews)
        shop.rating = (
            sum(r.rating for r in shop_reviews) / len(shop_reviews) if shop_reviews else 0.0
        )
        session.add(shop)


def create_review(
    session: Session, user: models.User, data: schemas.ReviewCreate
) -> schemas.ReviewRead:
    item = session.get(models.OrderItem, data.order_item_id)
    if item is None:
        raise LookupError("ไม่พบรายการสินค้าที่ต้องการรีวิว")

    order = item.order
    if order is None or order.buyer_id != user.id:
        raise PermissionError("รีวิวได้เฉพาะสินค้าที่คุณสั่งซื้อเอง")
    if order.status not in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
        raise ValueError("รีวิวได้หลังจากกดรับสินค้าแล้วเท่านั้น")
    if item.review is not None:
        raise ValueError("คุณรีวิวสินค้ารายการนี้ไปแล้ว")

    review = models.Review(
        product_id=item.product_id,
        shop_id=order.shop_id,
        user_id=user.id,
        order_item_id=item.id,
        rating=data.rating,
        comment=data.comment.strip(),
    )
    session.add(review)
    session.flush()

    _recalculate_ratings(session, item.product_id, order.shop_id)

    # ถ้ารีวิวครบทุกรายการในออเดอร์แล้ว ถือว่าออเดอร์เสร็จสมบูรณ์
    # ต้อง query ตาราง Review ตรงๆ ไม่ใช้ item.review เพราะ relationship ถูก cache ไว้
    # ตั้งแต่ตอนตรวจว่ารีวิวซ้ำหรือยัง (ยังเป็น None อยู่) จะทำให้เช็คผิดเสมอ
    reviewed_item_ids = {
        r.order_item_id
        for r in session.exec(
            select(models.Review).where(
                models.Review.order_item_id.in_([i.id for i in order.items])
            )
        ).all()
    }
    if all(i.id in reviewed_item_ids for i in order.items):
        order.status = OrderStatus.COMPLETED
        session.add(order)

    session.commit()
    session.refresh(review)
    return schemas.ReviewRead(
        id=review.id,
        product_id=review.product_id,
        rating=review.rating,
        comment=review.comment,
        user_name=user.name,
        created_at=review.created_at,
    )


def list_reviews_by_product(session: Session, product_id: int) -> List[schemas.ReviewRead]:
    reviews = session.exec(
        select(models.Review)
        .where(models.Review.product_id == product_id)
        .order_by(models.Review.id.desc())
    ).all()
    return [
        schemas.ReviewRead(
            id=r.id,
            product_id=r.product_id,
            rating=r.rating,
            comment=r.comment,
            user_name=r.user.name if r.user else "ผู้ใช้",
            created_at=r.created_at,
        )
        for r in reviews
    ]


# =====================================================================
# Seller price dashboard (เฟส 1)
# =====================================================================

_TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
              "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def _th_date(d) -> str:
    """5 ต.ค. 2569 (พ.ศ.) — วันที่ตามเวลาไทย"""
    if isinstance(d, datetime):
        d = (pricing.naive(d) + timedelta(hours=7)).date()
    return f"{d.day} {_TH_MONTHS[d.month - 1]} {d.year + 543}"


def _cart_counts(session: Session, product_ids: List[int]) -> dict:
    """{product_id: (จำนวนตะกร้าทั้งหมด, จำนวนตะกร้าของผู้ใช้ที่ล็อกอิน)} — นับเป็นจำนวน ไม่เปิดเผยตัวผู้ซื้อ"""
    counts = {pid: [set(), set()] for pid in product_ids}
    if not product_ids:
        return {}
    rows = session.exec(
        select(models.CartItem.product_id, models.Cart.id, models.Cart.user_id)
        .where(models.CartItem.cart_id == models.Cart.id)
        .where(models.CartItem.product_id.in_(product_ids))
    ).all()
    for pid, cart_id, user_id in rows:
        counts[pid][0].add(cart_id)
        if user_id is not None:
            counts[pid][1].add(cart_id)
    return {pid: (len(a), len(b)) for pid, (a, b) in counts.items()}


def seller_price_status(
    session: Session, shop: models.Shop, now: Optional[datetime] = None
) -> schemas.PriceStatus:
    """ข้อมูล dashboard ราคาของร้าน: ราคาก่อนลดที่ระบบใช้, คำเตือนขึ้นราคาก่อนลด, ตะกร้าที่ถือสินค้าอยู่"""
    from app import config

    now_n = pricing.naive(now) if now is not None else pricing.utcnow_naive()
    in_grace = pricing.grace_active(now_n)
    grace_end = pricing.grace_end_date()
    raise_days = config.PRICE_RAISE_WINDOW_DAYS
    raise_pct = config.PRICE_RAISE_PERCENT

    products = session.exec(
        select(models.Product)
        .where(models.Product.shop_id == shop.id)
        .order_by(models.Product.id.desc())
    ).all()
    counts = _cart_counts(session, [p.id for p in products])

    items = []
    for product in products:
        ref = session.get(models.SkuPriceRef, product.id)
        display = pricing.compute_display(product, ref, now=now_n)
        warnings: List[schemas.PriceWarning] = []
        rows = pricing.history(session, product.id)

        if display.raise_flagged and ref is not None and ref.price_since is not None:
            since = pricing.naive(ref.price_since)
            pct, raised_at = pricing.max_increase(
                [r for r in rows if pricing.naive(r.valid_from) < since],
                since - timedelta(days=raise_days), since, include_end=False,
            )
            raised_txt = f"คุณขึ้นราคา {pct:.0f}%" + (
                f" เมื่อ {_th_date(raised_at)}" if raised_at else ""
            ) + f" ซึ่งอยู่ภายใน {raise_days} วันก่อนเริ่มลดราคา"
            back_txt = (
                f" ถ้าต้องการให้แสดง % อีกครั้ง ให้เริ่มลดราคารอบใหม่ตั้งแต่ "
                f"{_th_date(raised_at + timedelta(days=raise_days))} เป็นต้นไป"
                if raised_at else ""
            )
            if display.discount_hidden:
                warnings.append(schemas.PriceWarning(
                    code="raise_before_discount",
                    message=(
                        f"{raised_txt} ระบบจึงไม่แสดง % ส่วนลดให้ผู้ซื้อเห็น "
                        f"(ยังแสดงราคาก่อนลด ฿{display.ref_price:,} ตามปกติ)" + back_txt
                    ),
                ))
            else:
                warnings.append(schemas.PriceWarning(
                    code="raise_before_discount_grace",
                    message=(
                        f"{raised_txt} ตอนนี้อยู่ในช่วงผ่อนผัน ผู้ซื้อยังเห็น % ส่วนลดตามปกติ "
                        f"แต่ตั้งแต่ {_th_date(grace_end)} ระบบจะซ่อน % ส่วนลดของสินค้าที่เข้าเงื่อนไขนี้"
                        + back_txt
                    ),
                ))
        elif display.ref_price is None:
            # ยังไม่ได้ลดราคา: เตือนล่วงหน้าถ้าเพิ่งขึ้นราคา (ถ้าลดตอนนี้ % จะถูกซ่อน)
            pct, raised_at = pricing.max_increase(
                rows, now_n - timedelta(days=raise_days), now_n, include_end=True
            )
            if pct is not None and pct >= raise_pct and raised_at is not None:
                ok_from = raised_at + timedelta(days=raise_days)
                msg = (
                    f"คุณขึ้นราคา {pct:.0f}% เมื่อ {_th_date(raised_at)} ถ้าลดราคาก่อน "
                    f"{_th_date(ok_from)} ระบบจะไม่แสดง % ส่วนลด (กฎขึ้นราคา ≥ {raise_pct:.0f}% "
                    f"ภายใน {raise_days} วันก่อนลด)"
                )
                if in_grace:
                    msg += f" — ช่วงผ่อนผันถึง {_th_date(grace_end)} ยังแสดง % ตามปกติ"
                warnings.append(schemas.PriceWarning(code="recent_raise", message=msg))

        holding, eligible = counts.get(product.id, (0, 0))
        items.append(schemas.PriceStatusItem(
            product_id=product.id,
            name=product.name,
            is_active=product.is_active,
            price=product.price,
            in_stock=product.stock > 0,
            ref_price=display.ref_price,
            min_30d=ref.min_30d if ref else None,
            discount_percent=display.discount_percent,
            discount_hidden=display.discount_hidden,
            max_increase_14d_percent=ref.max_increase_14d if ref else None,
            warnings=warnings,
            carts_holding=holding,
            carts_notice_eligible=eligible,
            ref_updated_at=ref.updated_at if ref else None,
        ))

    return schemas.PriceStatus(
        grace=schemas.GraceInfo(
            enabled=config.PRICE_GRACE_ENABLED,
            active=in_grace,
            starts_at=config.PRICE_GRACE_START,
            ends_at=grace_end if config.PRICE_GRACE_ENABLED else None,
        ),
        rules=schemas.PriceRules(
            ref_window_days=config.PRICE_REF_WINDOW_DAYS,
            raise_window_days=raise_days,
            raise_percent=raise_pct,
            notice_min_percent=config.CART_NOTICE_MIN_PERCENT,
            notice_min_baht=config.CART_NOTICE_MIN_BAHT,
        ),
        items=items,
    )


# =====================================================================
# เฟส 2: แม่แบบสเปก / ข้อเสนอสเปกจาก AI / ค่าส่ง / จังหวัด / ถาดเทียบ
# =====================================================================

def category_attributes(session: Session, category_id: int) -> List[schemas.AttributeTemplateRead]:
    if session.get(models.Category, category_id) is None:
        raise LookupError("ไม่พบหมวดหมู่นี้")
    return [
        schemas.AttributeTemplateRead(
            key=a.key, name_th=a.name_th, unit=a.unit, data_type=a.data_type,
            options=specs.options_of(a), group_name=a.group_name, better=a.better,
            required=a.required, sort=a.sort, badge_label=a.badge_label,
        )
        for a in specs.template(session, category_id)
    ]


def list_spec_suggestions(session: Session, product: models.Product) -> List[schemas.SpecSuggestionRead]:
    """ข้อเสนอที่ยังรอผู้ขายตัดสินใจ — เฉพาะ key ที่ยังไม่ได้กรอก และยังอยู่ในแม่แบบหมวดปัจจุบัน"""
    tmpl = {a.key: a for a in specs.template(session, product.category_id)}
    filled = specs.values_of(session, product.id)
    rows = session.exec(
        select(models.SpecSuggestion).where(
            models.SpecSuggestion.product_id == product.id,
            models.SpecSuggestion.status == "pending",
        ).order_by(models.SpecSuggestion.id)
    ).all()
    out = []
    for r in rows:
        a = tmpl.get(r.key)
        if a is None or r.key in filled:
            continue
        out.append(schemas.SpecSuggestionRead(
            id=r.id, key=r.key, name_th=a.name_th, unit=a.unit, value_num=r.value_num,
            value_text=r.value_text, display=specs.display(a, r.value_num, r.value_text),
        ))
    return out


def resolve_spec_suggestions(
    session: Session, product: models.Product, keys: List[str], confirm: bool
) -> None:
    """ผู้ขายกดยืนยัน (บันทึกเป็นสเปก source=ai_confirmed) หรือปัดทิ้ง — เฉพาะ key ที่ส่งมา"""
    pending = {s.key: s for s in session.exec(
        select(models.SpecSuggestion).where(
            models.SpecSuggestion.product_id == product.id,
            models.SpecSuggestion.status == "pending",
            models.SpecSuggestion.key.in_(keys or [""]),
        )
    ).all()}
    filled = specs.values_of(session, product.id)
    for key, sug in pending.items():
        if confirm:
            clean = specs.validate_values(
                session, product.category_id,
                [{"key": key, "value_num": sug.value_num, "value_text": sug.value_text}],
            )
            if clean and key not in filled:
                session.add(models.ProductAttributeValue(
                    product_id=product.id, source="ai_confirmed", **clean[0]
                ))
        sug.status = "confirmed" if confirm else "dismissed"
        session.add(sug)
    session.commit()


def _shipping_settings(session: Session, shop_id: int) -> schemas.ShippingSettings:
    cfg = shipping.get_shop_shipping(session, shop_id)
    rates = sorted(
        shipping.get_region_rates(session, shop_id),
        key=lambda r: shipping.REGIONS.index(r.region) if r.region in shipping.REGIONS else 99,
    )
    return schemas.ShippingSettings(
        flat_rate=cfg.flat_rate, free_over=cfg.free_over, days_min=cfg.days_min, days_max=cfg.days_max,
        region_rates=[
            schemas.RegionRate(region=r.region, rate=r.rate, days_min=r.days_min, days_max=r.days_max)
            for r in rates
        ],
    )


def get_shop_shipping(session: Session, shop: models.Shop) -> schemas.ShippingSettings:
    return _shipping_settings(session, shop.id)


def _check_days(dmin: int, dmax: int) -> None:
    if dmin < 0 or dmax < dmin or dmax > 60:
        raise ValueError("ระยะเวลาส่งไม่ถูกต้อง (0 ≤ เร็วสุด ≤ ช้าสุด ≤ 60 วัน)")


def update_shop_shipping(
    session: Session, shop: models.Shop, data: schemas.ShippingSettings
) -> schemas.ShippingSettings:
    if data.flat_rate < 0 or (data.free_over is not None and data.free_over < 0):
        raise ValueError("ค่าส่งต้องไม่ติดลบ")
    _check_days(data.days_min, data.days_max)
    seen = set()
    for r in data.region_rates:
        if r.region not in shipping.REGIONS:
            raise ValueError(f"ไม่รู้จักภาค {r.region}")
        if r.region in seen:
            raise ValueError(f"ตั้งค่าภาค {r.region} ซ้ำ")
        if r.rate < 0:
            raise ValueError("ค่าส่งต้องไม่ติดลบ")
        _check_days(r.days_min, r.days_max)
        seen.add(r.region)

    cfg = session.get(models.ShopShipping, shop.id) or models.ShopShipping(shop_id=shop.id)
    cfg.flat_rate, cfg.free_over = data.flat_rate, data.free_over
    cfg.days_min, cfg.days_max = data.days_min, data.days_max
    session.add(cfg)
    for old in shipping.get_region_rates(session, shop.id):
        session.delete(old)
    session.flush()
    for r in data.region_rates:
        session.add(models.ShopShippingRegion(shop_id=shop.id, **r.model_dump()))
    session.commit()
    return _shipping_settings(session, shop.id)


def get_account_province(session: Session, user: models.User) -> schemas.AccountProvince:
    prov, source = shipping.resolve_user_province(session, user)
    return schemas.AccountProvince(province=prov, region=shipping.region_of(prov), source=source)


def set_account_province(session: Session, user: models.User, raw: Optional[str]) -> schemas.AccountProvince:
    if raw is None or not raw.strip():
        user.province = None
    else:
        prov = shipping.normalize_province(raw)
        if prov is None:
            raise ValueError("ไม่พบจังหวัดนี้ (ต้องเป็น 1 ใน 77 จังหวัด)")
        user.province = prov
    session.add(user)
    session.commit()
    return get_account_province(session, user)


def cart_shipping_quote(
    session: Session, token: str, province: Optional[str], user: Optional[models.User] = None
) -> schemas.ShippingQuote:
    """ใบเสนอค่าส่งของตะกร้า แยกตามร้าน — ใช้ engine เดียวกับ checkout"""
    prov = shipping.normalize_province(province)
    if province and prov is None:
        raise ValueError("ไม่พบจังหวัดนี้")
    if prov is None and user is not None:
        prov, _ = shipping.resolve_user_province(session, user)
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    by_shop: dict = {}
    for item in (cart.items if cart else []):
        p = item.product
        if p is None or not p.is_active:
            continue
        by_shop.setdefault(p.shop_id, []).append((p, item.quantity))
    shops = []
    for shop_id, entries in by_shop.items():
        q = shipping.quote(session, shop_id, entries, prov)
        shop = session.get(models.Shop, shop_id) if shop_id else None
        shops.append(schemas.ShopQuote(shop_id=shop_id, shop_name=shop.name if shop else "", **q))
    ship_total = sum(s.fee for s in shops)
    return schemas.ShippingQuote(
        province=prov, region=shipping.region_of(prov), shops=shops,
        shipping_total=ship_total, grand_total=sum(s.subtotal for s in shops) + ship_total,
    )


def _valid_compare_ids(session: Session, ids: List[int]) -> List[int]:
    ids = list(dict.fromkeys(ids))
    return [i for i in ids if session.get(models.Product, i) is not None]


def get_compare_list(session: Session, user: models.User) -> schemas.CompareIds:
    row = session.get(models.CompareList, user.id)
    ids = json.loads(row.ids_json) if row else []
    return schemas.CompareIds(ids=_valid_compare_ids(session, ids))


def set_compare_list(session: Session, user: models.User, ids: List[int]) -> schemas.CompareIds:
    if len(set(ids)) > 4:
        raise ValueError("ถาดเทียบใส่ได้สูงสุด 4 ชิ้น")
    ids = _valid_compare_ids(session, ids)
    row = session.get(models.CompareList, user.id) or models.CompareList(user_id=user.id)
    row.ids_json = json.dumps(ids)
    row.updated_at = pricing.utcnow_naive()
    session.add(row)
    session.commit()
    return schemas.CompareIds(ids=ids)
