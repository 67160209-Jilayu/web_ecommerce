"""Router หมวดหมู่สินค้า"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, schemas
from app.database import get_session

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[schemas.CategoryRead])
def list_categories(session: Session = Depends(get_session)):
    """คืนหมวดหมู่ทั้งหมด ใช้ทำแถบหมวดหมู่หน้าแรกและตัวเลือกตอนลงขายสินค้า"""
    return crud.list_categories(session)


@router.get("/{category_id}/attributes", response_model=list[schemas.AttributeTemplateRead])
def list_category_attributes(category_id: int, session: Session = Depends(get_session)):
    """แม่แบบสเปกของหมวด — ฟอร์มผู้ขายใช้สร้างช่องเลือก/ช่องตัวเลข (หน่วยล็อกไว้)"""
    try:
        return crud.category_attributes(session, category_id)
    except LookupError as err:
        raise HTTPException(status_code=404, detail=str(err))
