"""ฟังก์ชันอ่าน/เขียนข้อมูลจริงกับฐานข้อมูล (แทน mock data ของสัปดาห์ 1)"""
from typing import List, Optional

from sqlmodel import Session, select

from app import models, schemas


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
