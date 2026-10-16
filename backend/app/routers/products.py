"""Router สินค้า — อ่านได้ทุกคน แต่ลงขาย/แก้ไข/ปิดขายต้องเป็นเจ้าของร้านเท่านั้น"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import compare, crud, matching, models, review_summary, schemas, spec_suggest
from app.database import get_session
from app.routers.auth import get_current_user, get_optional_user
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


# ---------------------------------------------------------------- เฟส 2

def _active_product(product_id: int, session: Session) -> models.Product:
    product = session.get(models.Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    return product


@router.get("/{product_id}/same-model", response_model=list[schemas.SameModelRow])
def same_model(
    product_id: int,
    province: Optional[str] = Query(None, description="จังหวัดผู้ซื้อ (คิดค่าส่ง)"),
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """ร้านอื่นที่ขายรุ่นนี้ (บาร์โค้ด หรือ แบรนด์+รหัสรุ่นตรงกัน) — [] = ไม่ต้องแสดงส่วนนี้"""
    product = _active_product(product_id, session)
    if not province and current_user is not None:
        province = crud.get_account_province(session, current_user).province
    return compare.same_model(session, product, province)


@router.get("/{product_id}/similar", response_model=list[schemas.ProductRead])
def similar_products(
    product_id: int,
    limit: int = Query(3, ge=1, le=10),
    session: Session = Depends(get_session),
):
    """สินค้าหมวดเดียวกันที่ราคาใกล้เคียง สำหรับ "เทียบกับสินค้าคล้ายกัน" """
    product = _active_product(product_id, session)
    return [crud._to_product_read(p) for p in compare.similar(session, product, limit)]


@router.get("/{product_id}/spec-suggestions", response_model=list[schemas.SpecSuggestionRead])
def list_spec_suggestions(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ค่าสเปกที่ AI เสนอ (รอผู้ขายยืนยัน) — เฉพาะเจ้าของร้าน"""
    product = _load_own_product(product_id, session, current_user)
    return crud.list_spec_suggestions(session, product)


@router.post("/{product_id}/spec-suggestions/generate", response_model=list[schemas.SpecSuggestionRead])
def generate_spec_suggestions(
    product_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ให้ AI อ่านคำอธิบายแล้วเสนอสเปกเดี๋ยวนี้ (วันละครั้งต่อสินค้า; ไม่มี LLM → [])"""
    product = _load_own_product(product_id, session, current_user)
    try:
        spec_suggest.generate_for_product(session, product)
    except PermissionError as err:
        raise HTTPException(status_code=429, detail=str(err))
    return crud.list_spec_suggestions(session, product)


@router.post("/{product_id}/spec-suggestions/confirm", response_model=schemas.ProductRead)
def confirm_spec_suggestions(
    product_id: int,
    data: schemas.KeysIn,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ยืนยันข้อเสนอที่เลือก → บันทึกเป็นสเปกของสินค้า (source = ai_confirmed)"""
    product = _load_own_product(product_id, session, current_user)
    crud.resolve_spec_suggestions(session, product, data.keys, confirm=True)
    session.refresh(product)
    return crud._to_product_read(product)


@router.post("/{product_id}/spec-suggestions/dismiss", status_code=204)
def dismiss_spec_suggestions(
    product_id: int,
    data: schemas.KeysIn,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ปัดข้อเสนอที่ไม่ถูกต้องทิ้ง"""
    product = _load_own_product(product_id, session, current_user)
    crud.resolve_spec_suggestions(session, product, data.keys, confirm=False)



# ---------------------------------------------------------------- เฟส 4

@router.get("/{product_id}/maybe-same", response_model=list[schemas.MaybeSameRow])
def maybe_same(
    product_id: int,
    province: Optional[str] = Query(None),
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """ร้านอื่นที่ "อาจเป็นรุ่นเดียวกัน" (จับคู่จากชื่อ+แบรนด์+สเปก) — แยกจากรายการที่ตรงทุกตัว [] = ไม่แสดง"""
    product = _active_product(product_id, session)
    if not province and current_user is not None:
        province = crud.get_account_province(session, current_user).province
    return matching.maybe_same(session, product, province)


@router.get("/{product_id}/review-summary", response_model=schemas.ReviewSummaryRead)
def get_review_summary(product_id: int, session: Session = Depends(get_session)):
    """สรุป "ลูกค้าชม / ลูกค้าติ" จากรีวิวจริง (ต้องมีรีวิวถึงเกณฑ์) — ไม่มีก็คืน available=false"""
    product = _active_product(product_id, session)
    return review_summary.get_summary(session, product)
