"""Router คำสั่งซื้อ — checkout, ติดตามสถานะ, เปลี่ยนสถานะฝั่งผู้ซื้อ/ผู้ขาย

Flow สถานะ:
  PENDING_PAYMENT --(pay / COD ข้ามขั้นนี้)--> PAID --(ship)--> SHIPPED --(receive)--> DELIVERED
  PENDING_PAYMENT / PAID --(cancel + คืน stock)--> CANCELLED
  DELIVERED --(รีวิวครบทุกรายการ)--> COMPLETED
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user
from app.routers.shops import require_own_shop

router = APIRouter(prefix="/orders", tags=["orders"])


def _handle(fn, *args, **kwargs):
    """แปลง exception จาก crud เป็น HTTP status ที่เหมาะสม (ใช้ซ้ำทุก action)"""
    try:
        return fn(*args, **kwargs)
    except LookupError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/checkout", response_model=list[schemas.OrderRead], status_code=201)
def checkout(
    token: str,
    data: schemas.CheckoutRequest,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """แปลงตะกร้าเป็นคำสั่งซื้อ — ถ้ามีสินค้าหลายร้านจะถูกแยกเป็นหลายออเดอร์อัตโนมัติ"""
    return _handle(crud.checkout, session, token, current_user, data)


@router.get("/me", response_model=list[schemas.OrderRead])
def list_my_orders(
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """คำสั่งซื้อที่ฉันเป็นผู้ซื้อ"""
    return crud.list_orders_buying(session, current_user)


@router.get("/selling", response_model=list[schemas.OrderRead])
def list_selling_orders(
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """คำสั่งซื้อที่เข้ามาที่ร้านฉัน (สำหรับผู้ขาย)"""
    return crud.list_orders_selling(session, shop)


@router.get("/{order_id}", response_model=schemas.OrderRead)
def get_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """รายละเอียดคำสั่งซื้อ — เปิดดูได้เฉพาะผู้ซื้อกับเจ้าของร้านเท่านั้น"""
    return _handle(crud.get_order_for_user, session, order_id, current_user)


@router.post("/{order_id}/pay", response_model=schemas.OrderRead)
def pay_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ยืนยันการชำระเงิน (mock — ไม่ได้ต่อ payment gateway จริง)"""
    return _handle(crud.pay_order, session, order_id, current_user)


@router.post("/{order_id}/ship", response_model=schemas.OrderRead)
def ship_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ร้านค้ากดจัดส่งสินค้า"""
    return _handle(crud.ship_order, session, order_id, current_user)


@router.post("/{order_id}/receive", response_model=schemas.OrderRead)
def receive_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ผู้ซื้อกดยืนยันว่าได้รับสินค้าแล้ว (หลังจากนี้จึงรีวิวได้)"""
    return _handle(crud.receive_order, session, order_id, current_user)


@router.post("/{order_id}/cancel", response_model=schemas.OrderRead)
def cancel_order(
    order_id: int,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ยกเลิกคำสั่งซื้อ (ทำได้ทั้งผู้ซื้อและร้าน ถ้ายังไม่จัดส่ง) — คืน stock อัตโนมัติ"""
    return _handle(crud.cancel_order, session, order_id, current_user)
