"""Router ตะกร้าสินค้า — สัปดาห์ 3: ย้ายจาก localStorage มาเป็น DB จริง

ตะกร้าผูกกับ browser ผ่าน `token` (สร้างฝั่ง frontend เก็บใน localStorage) แทน user_id
เพราะยังไม่มีระบบล็อกอิน (รอสัปดาห์ 4 ถึงจะผูกกับผู้ใช้จริง)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, schemas
from app.database import get_session

router = APIRouter(prefix="/cart", tags=["cart"])


@router.get("/{token}", response_model=schemas.CartRead)
def get_cart(token: str, session: Session = Depends(get_session)):
    """คืนตะกร้าตาม token — ถ้ายังไม่เคยเพิ่มสินค้าเลยจะได้ตะกร้าว่าง ไม่ error"""
    return crud.get_cart(session, token)


@router.post("/{token}/items", response_model=schemas.CartRead, status_code=201)
def add_item(
    token: str, data: schemas.CartItemCreate, session: Session = Depends(get_session)
):
    """เพิ่มสินค้าลงตะกร้า (ถ้ามีอยู่แล้วจะบวกจำนวนเพิ่ม ไม่เกิน stock คงเหลือ)"""
    try:
        return crud.add_cart_item(session, token, data)
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
