"""Router ตะกร้าสินค้า

ตะกร้าผูกกับ browser ผ่าน `token` (frontend สร้างเก็บใน localStorage)
เมื่อผู้ใช้ล็อกอิน จะเรียก /merge เพื่อผูกตะกร้านั้นเข้ากับบัญชี
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user, get_optional_user

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("/{token}", response_model=schemas.CartRead)
def get_cart(token: str, session: Session = Depends(get_session)):
    """คืนตะกร้าตาม token — ถ้ายังไม่เคยเพิ่มสินค้าเลยจะได้ตะกร้าว่าง ไม่ error"""
    return crud.get_cart(session, token)


@router.post("/{token}/items", response_model=schemas.CartRead, status_code=201)
def add_item(
    token: str,
    data: schemas.CartItemCreate,
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """เพิ่มสินค้าลงตะกร้า (ถ้ามีอยู่แล้วจะบวกจำนวนเพิ่ม ไม่เกิน stock คงเหลือ)"""
    try:
        return crud.add_cart_item(session, token, data, user=current_user)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.patch("/{token}/items/{product_id}", response_model=schemas.CartRead)
def update_item(
    token: str,
    product_id: int,
    data: schemas.CartItemUpdate,
    session: Session = Depends(get_session),
):
    """ปรับจำนวนสินค้าในตะกร้า (ตั้งเป็น 0 หรือน้อยกว่า = ลบออกจากตะกร้า)"""
    try:
        return crud.update_cart_item(session, token, product_id, data.quantity)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@router.delete("/{token}/items/{product_id}", response_model=schemas.CartRead)
def remove_item(token: str, product_id: int, session: Session = Depends(get_session)):
    """ลบสินค้าออกจากตะกร้า"""
    try:
        return crud.remove_cart_item(session, token, product_id)
    except ValueError as err:
        raise HTTPException(status_code=404, detail=str(err))


@router.post("/{token}/merge", response_model=schemas.CartRead)
def merge_cart(
    token: str,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ผูกตะกร้า guest เข้ากับบัญชีที่เพิ่งล็อกอิน (รวมกับตะกร้าเดิมของบัญชีถ้ามี)"""
    return crud.merge_cart_to_user(session, token, current_user)
