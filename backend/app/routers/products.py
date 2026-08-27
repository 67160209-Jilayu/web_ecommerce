"""Router สินค้า — อ่านได้ทุกคน แต่ลงขาย/แก้ไข/ปิดขายต้องเป็นเจ้าของร้านเท่านั้น"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user
from app.routers.shops import require_own_shop

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[schemas.ProductRead])
def list_products(
    search: Optional[str] = Query(None, description="คำค้นหาชื่อ/คำอธิบายสินค้า"),
    category_id: Optional[int] = Query(None, description="กรองตามหมวดหมู่"),
    min_price: Optional[int] = Query(None, description="ราคาต่ำสุด"),
    max_price: Optional[int] = Query(None, description="ราคาสูงสุด"),
    sort: str = Query("latest", description="latest | price_asc | price_desc | popular | rating"),
    session: Session = Depends(get_session),
):
    """คืนสินค้าที่เปิดขายอยู่ พร้อมตัวกรองและการเรียงลำดับ"""
    return crud.list_products(
        session,
        search=search,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )


@router.get("/me", response_model=list[schemas.ProductRead])
def list_my_products(
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """สินค้าทั้งหมดในร้านฉัน (รวมที่ปิดขายแล้ว) สำหรับแดชบอร์ดผู้ขาย"""
    return crud.list_products_by_shop_owner(session, shop.id)


@router.get("/{product_id}", response_model=schemas.ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)):
    """รายละเอียดสินค้ารายชิ้น พร้อมรูป/วิดีโอทั้งหมด"""
    product = crud.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    return product


@router.get("/{product_id}/reviews", response_model=list[schemas.ReviewRead])
def list_product_reviews(product_id: int, session: Session = Depends(get_session)):
    """รีวิวทั้งหมดของสินค้าชิ้นนี้"""
    if session.get(models.Product, product_id) is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    return crud.list_reviews_by_product(session, product_id)


@router.post("", response_model=schemas.ProductRead, status_code=201)
def create_product(
    data: schemas.ProductCreate,
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """ลงขายสินค้าใหม่ในร้านของตัวเอง"""
    try:
        return crud.create_product(session, shop, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


def _load_own_product(
    product_id: int, session: Session, current_user: models.User
) -> models.Product:
    product = session.get(models.Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    if product.shop is None or product.shop.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์แก้ไขสินค้าของร้านอื่น")
    return product


@router.patch("/{product_id}", response_model=schemas.ProductRead)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """แก้ไขสินค้า — เฉพาะเจ้าของร้านเท่านั้น"""
    product = _load_own_product(product_id, session, current_user)
    try:
        return crud.update_product(session, product, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ปิดขายสินค้า (soft delete) — ไม่ลบจริงเพราะคำสั่งซื้อเก่ายังอ้างอิงอยู่"""
    product = _load_own_product(product_id, session, current_user)
    crud.deactivate_product(session, product)
