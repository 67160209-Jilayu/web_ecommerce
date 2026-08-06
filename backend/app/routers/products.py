"""Router สินค้า — สัปดาห์ 2: อ่าน/เขียนจาก PostgreSQL จริงผ่าน SQLModel (เลิกใช้ mock data แล้ว)"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import crud, schemas
from app.database import get_session

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[schemas.ProductRead])
def list_products(
    search: Optional[str] = Query(None, description="คำค้นหาชื่อสินค้า"),
    session: Session = Depends(get_session),
):
    """คืนรายการสินค้าทั้งหมด หรือกรองตามคำค้นหาถ้ามี query param `search`"""
    return crud.list_products(session, search=search)


@router.get("/{product_id}", response_model=schemas.ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)):
    """คืนข้อมูลสินค้ารายชิ้นตาม id"""
    product = crud.get_product(session, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    return product


@router.post("", response_model=schemas.ProductRead, status_code=201)
def create_product(data: schemas.ProductCreate, session: Session = Depends(get_session)):
    """เพิ่มสินค้าใหม่เข้าฐานข้อมูล (ยังไม่มีระบบสิทธิ์ผู้ใช้ รอสัปดาห์ 4)"""
    try:
        return crud.create_product(session, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
