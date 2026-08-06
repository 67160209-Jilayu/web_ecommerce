"""Router ร้านค้า — เพิ่มใหม่ในสัปดาห์ 2 เพื่อรองรับความสัมพันธ์ Shop 1—* Product"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import crud, schemas
from app.database import get_session

router = APIRouter(prefix="/shops", tags=["shops"])


@router.get("", response_model=list[schemas.ShopRead])
def list_shops(session: Session = Depends(get_session)):
    """คืนรายชื่อร้านค้าทั้งหมด"""
    return crud.list_shops(session)


@router.post("", response_model=schemas.ShopRead, status_code=201)
def create_shop(data: schemas.ShopCreate, session: Session = Depends(get_session)):
    """เพิ่มร้านค้าใหม่ (ใช้ shop_id ที่ได้ตอนสร้างสินค้าใหม่ผ่าน POST /api/products)"""
    return crud.create_shop(session, data)
