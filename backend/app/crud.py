"""ฟังก์ชันอ่าน/เขียนข้อมูลจริงกับฐานข้อมูล (แทน mock data ของสัปดาห์ 1)"""
from typing import List, Optional

from sqlmodel import Session, select

from app import models, schemas
from app.auth import hash_password, verify_password


def _to_product_read(product: models.Product) -> schemas.ProductRead:
    return schemas.ProductRead(
        id=product.id,
        name=product.name,
        price=product.price,
        original_price=product.original_price,
        image=product.image,
        shop_name=product.shop.name if product.shop else "ไม่ระบุร้าน",
        rating=product.rating,
        sold=product.sold,
        stock=product.stock,
        free_shipping=product.free_shipping,
        category=product.category,
        description=product.description,
    )


def list_products(
    session: Session, search: Optional[str] = None
) -> List[schemas.ProductRead]:
    products = session.exec(select(models.Product)).all()
    if search:
        keyword = search.strip().lower()
        products = [p for p in products if keyword in p.name.lower()]
    return [_to_product_read(p) for p in products]


def get_product(session: Session, product_id: int) -> Optional[schemas.ProductRead]:
    product = session.get(models.Product, product_id)
    return _to_product_read(product) if product else None


def create_product(
    session: Session, data: schemas.ProductCreate
) -> schemas.ProductRead:
    shop = session.get(models.Shop, data.shop_id)
    if shop is None:
        raise ValueError("ไม่พบร้านค้าตาม shop_id ที่ระบุ")

    product = models.Product(**data.dict())
    session.add(product)
    session.commit()
    session.refresh(product)
    return _to_product_read(product)


def list_shops(session: Session) -> List[models.Shop]:
    return session.exec(select(models.Shop)).all()


def create_shop(session: Session, data: schemas.ShopCreate) -> models.Shop:
    shop = models.Shop(**data.dict())
    session.add(shop)
    session.commit()
    session.refresh(shop)
    return shop


# ---------- Cart (สัปดาห์ 3) ----------


def _to_cart_read(cart: models.Cart) -> schemas.CartRead:
    items = []
    total = 0
    for item in cart.items:
        if item.product is None:  # กันกรณีสินค้าถูกลบไปแล้วแต่ยังค้างในตะกร้า
            continue
        subtotal = item.product.price * item.quantity
        total += subtotal
        items.append(
            schemas.CartItemRead(
                product_id=item.product_id,
                name=item.product.name,
                price=item.product.price,
                image=item.product.image,
                stock=item.product.stock,
                quantity=item.quantity,
            )
        )
    return schemas.CartRead(token=cart.token, items=items, total=total)


def get_cart(session: Session, token: str) -> schemas.CartRead:
    """ถ้ายังไม่เคยมีตะกร้านี้ใน DB (ยังไม่เคยเพิ่มสินค้าเลย) คืนตะกร้าว่างแทนการ error"""
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
    session: Session, token: str, data: schemas.CartItemCreate
) -> schemas.CartRead:
    # Edge Case (จากเอกสาร User Journey): "สินค้าหมดสต็อกระหว่างที่ลูกค้ากำลังเช็คเอาท์"
    # ล็อก row สินค้าไว้ระหว่าง transaction (SELECT ... FOR UPDATE) กันสองคำขอพร้อมกัน
    # อ่าน stock ค่าเดิมแล้วเผลอเพิ่มลงตะกร้าเกินจำนวนที่มีจริง (race condition)
    product = session.exec(
        select(models.Product).where(models.Product.id == data.product_id).with_for_update()
    ).first()
    if product is None:
        raise ValueError("ไม่พบสินค้านี้")

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
        item.quantity = min(quantity, product.stock)
        session.add(item)
    session.commit()
    session.refresh(cart)
    return _to_cart_read(cart)


def remove_cart_item(session: Session, token: str, product_id: int) -> schemas.CartRead:
    return update_cart_item(session, token, product_id, 0)


# ---------- Auth (สัปดาห์ 4) ----------


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
