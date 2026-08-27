"""ฟังก์ชันอ่าน/เขียนข้อมูลจริงกับฐานข้อมูล

รวม business logic ทั้งหมดไว้ที่นี่ ให้ router ทำหน้าที่แค่รับ-ส่ง HTTP และแปลง error
เป็น status code เท่านั้น
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app import models, schemas
from app.auth import hash_password, verify_password
from app.models import OrderStatus, PaymentMethod
from app.storage import delete_files

SHIPPING_FEE = 40           # ค่าส่งต่อ 1 ร้าน
FREE_SHIPPING_MIN = 500     # ซื้อครบเท่านี้ต่อร้าน ส่งฟรี


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
    return schemas.ProductRead(
        id=product.id,
        name=product.name,
        price=product.price,
        original_price=product.original_price,
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
    )


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

    # ค้นหาด้วยคำ ทำในหน่วยความจำเพื่อให้รองรับภาษาไทยแบบไม่สนตัวพิมพ์เล็ก-ใหญ่
    if search:
        keyword = search.strip().lower()
        products = [
            p for p in products
            if keyword in p.name.lower() or keyword in (p.description or "").lower()
        ]

    return [_to_product_read(p) for p in products]


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

    for old in list(product.media):
        session.delete(old)
    session.flush()

    for i, item in enumerate(media):
        session.add(
            models.ProductMedia(
                product_id=product.id,
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

    product = models.Product(
        shop_id=shop.id,
        category_id=data.category_id,
        name=data.name.strip(),
        price=data.price,
        original_price=data.original_price,
        description=data.description,
        stock=data.stock,
        free_shipping=data.free_shipping,
        image=data.image or "📦",
    )
    session.add(product)
    session.flush()

    _replace_media(session, product, data.media)
    session.commit()
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
    if data.original_price is not None:
        product.original_price = data.original_price
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

    session.add(product)
    session.commit()
    session.refresh(product)
    return _to_product_read(product)


def deactivate_product(session: Session, product: models.Product) -> None:
    """ปิดขายแทนการลบจริง เพราะ OrderItem เก่ายังอ้างอิงสินค้านี้อยู่"""
    product.is_active = False
    session.add(product)
    session.commit()


# =====================================================================
# Cart
# =====================================================================

def _to_cart_read(cart: models.Cart) -> schemas.CartRead:
    items = []
    total = 0
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
            )
        )
    return schemas.CartRead(token=cart.token, items=items, total=total)


def get_cart(session: Session, token: str) -> schemas.CartRead:
    cart = session.exec(select(models.Cart).where(models.Cart.token == token)).first()
    if cart is None:
        return schemas.CartRead(token=token, items=[], total=0)
    return _to_cart_read(cart)


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
        existing.quantity = new_qty
        session.add(existing)
    else:
        session.add(
            models.CartItem(cart_id=cart.id, product_id=data.product_id, quantity=new_qty)
        )
    session.commit()
    session.refresh(cart)
    return _to_cart_read(cart)


def update_cart_item(
    session: Session, token: str, product_id: int, quantity: int
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
        session.delete(item)
    else:
        product = session.get(models.Product, product_id)
        item.quantity = min(quantity, product.stock) if product else quantity
        session.add(item)
    session.commit()
    session.refresh(cart)
    return _to_cart_read(cart)


def remove_cart_item(session: Session, token: str, product_id: int) -> schemas.CartRead:
    return update_cart_item(session, token, product_id, 0)


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
        return _to_cart_read(own_cart)

    user_cart = session.exec(
        select(models.Cart).where(
            models.Cart.user_id == user.id, models.Cart.id != guest_cart.id
        )
    ).first()

    if user_cart is None:
        guest_cart.user_id = user.id
        session.add(guest_cart)
        session.commit()
        session.refresh(guest_cart)
        return _to_cart_read(guest_cart)

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
            session.add(existing)
        else:
            session.add(
                models.CartItem(
                    cart_id=user_cart.id,
                    product_id=item.product_id,
                    quantity=min(item.quantity, cap),
                )
            )
        session.delete(item)
    session.commit()
    session.refresh(user_cart)
    return _to_cart_read(user_cart)


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
            session.delete(item)
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
    for shop_id, entries in by_shop.items():
        subtotal = sum(p.price * qty for p, qty in entries)
        all_free = all(p.free_shipping for p, _ in entries)
        shipping_fee = 0 if (all_free or subtotal >= FREE_SHIPPING_MIN) else SHIPPING_FEE

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

        created.append(order)

    # เคลียร์ตะกร้าหลังสร้างออเดอร์สำเร็จ
    for item in list(cart.items):
        session.delete(item)

    session.commit()
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
    for item in order.items:
        product = session.exec(
            select(models.Product).where(models.Product.id == item.product_id).with_for_update()
        ).first()
        if product:
            product.stock += item.quantity           # คืน stock
            if was_paid:
                product.sold = max(0, product.sold - item.quantity)
            session.add(product)

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = _now()
    session.add(order)
    session.commit()
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
