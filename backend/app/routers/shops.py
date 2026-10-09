"""Router ร้านค้า — ผู้ใช้ 1 บัญชีเปิดร้านได้ 1 ร้าน แล้วใช้ร้านนั้นลงขายสินค้า"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, dashboard, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user

router = APIRouter(prefix="/shops", tags=["shops"])


def require_own_shop(
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
) -> models.Shop:
    """dependency: ต้องล็อกอิน + ต้องเปิดร้านแล้ว (ใช้ซ้ำในทุก endpoint ฝั่งผู้ขาย)"""
    shop = crud.get_shop_by_owner(session, current_user.id)
    if shop is None:
        raise HTTPException(
            status_code=400, detail="คุณยังไม่มีร้านค้า กรุณาเปิดร้านก่อนใช้งานส่วนนี้"
        )
    return shop


@router.get("", response_model=list[schemas.ShopRead])
def list_shops(session: Session = Depends(get_session)):
    """คืนรายชื่อร้านค้าทั้งหมด"""
    return crud.list_shops(session)


@router.get("/me", response_model=schemas.ShopRead)
def get_my_shop(
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ร้านของฉัน — 404 ถ้ายังไม่เปิดร้าน (frontend ใช้เช็คว่าต้องแสดงฟอร์มเปิดร้านไหม)"""
    shop = crud.get_shop_by_owner(session, current_user.id)
    if shop is None:
        raise HTTPException(status_code=404, detail="คุณยังไม่มีร้านค้า")
    return crud._to_shop_read(session, shop)


@router.post("", response_model=schemas.ShopRead, status_code=201)
def create_shop(
    data: schemas.ShopCreate,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """เปิดร้านค้าใหม่ — 1 บัญชีเปิดได้ 1 ร้าน"""
    try:
        shop = crud.create_shop(session, current_user, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return crud._to_shop_read(session, shop)


@router.patch("/me", response_model=schemas.ShopRead)
def update_my_shop(
    data: schemas.ShopUpdate,
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """แก้ชื่อ/คำโปรยร้านของตัวเอง"""
    try:
        updated = crud.update_shop(session, shop, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return crud._to_shop_read(session, updated)


@router.get("/{shop_id}", response_model=schemas.ShopRead)
def get_shop(shop_id: int, session: Session = Depends(get_session)):
    """หน้าร้านแบบ public"""
    shop = crud.get_shop(session, shop_id)
    if shop is None:
        raise HTTPException(status_code=404, detail="ไม่พบร้านค้านี้")
    return crud._to_shop_read(session, shop)


@router.get("/{shop_id}/products", response_model=list[schemas.ProductRead])
def list_shop_products(shop_id: int, session: Session = Depends(get_session)):
    """สินค้าที่เปิดขายอยู่ในร้านนี้"""
    if crud.get_shop(session, shop_id) is None:
        raise HTTPException(status_code=404, detail="ไม่พบร้านค้านี้")
    return crud.list_products(session, shop_id=shop_id)


@router.get("/me/shipping", response_model=schemas.ShippingSettings)
def get_my_shipping(
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """ค่าส่งของร้านฉัน (ยังไม่ตั้ง = ค่าเริ่มต้น 40 บาท ส่งฟรีเมื่อครบ 500)"""
    return crud.get_shop_shipping(session, shop)


@router.put("/me/shipping", response_model=schemas.ShippingSettings)
def update_my_shipping(
    data: schemas.ShippingSettings,
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """ตั้งค่าส่ง: เรทเดียวทั้งประเทศ + เรทเฉพาะภาค (แทนทั้งชุด)"""
    try:
        return crud.update_shop_shipping(session, shop, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/me/dashboard", response_model=schemas.SellerDashboard)
def my_dashboard(
    shop: models.Shop = Depends(require_own_shop),
    session: Session = Depends(get_session),
):
    """สรุปยอดขายของร้านตัวเอง — ยอดขาย งานที่ต้องทำ ของขายดี ของใกล้หมด"""
    return dashboard.build(session, shop)
