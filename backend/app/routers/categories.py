"""Router หมวดหมู่สินค้า"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import crud, schemas
from app.database import get_session

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryRead])
def list_categories(session: Session = Depends(get_session)):
    """คืนหมวดหมู่ทั้งหมด ใช้ทำแถบหมวดหมู่หน้าแรกและตัวเลือกตอนลงขายสินค้า"""
    return crud.list_categories(session)
