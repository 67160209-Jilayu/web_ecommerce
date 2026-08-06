"""Router ร้านค้า — เพิ่มใหม่ในสัปดาห์ 2 เพื่อรองรับความสัมพันธ์ Shop 1—* Product"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user

router = APIRouter(prefix="/shops", tags=["shops"])


@router.get("", response_model=list[schemas.ShopRead])
def list_shops(session: Session = Depends(get_session)):
    """คืนรายชื่อร้านค้าทั้งหมด"""
    return crud.list_shops(session)


@router.post("", response_model=schemas.ShopRead, status_code=201)
def create_shop(
    data: schemas.ShopCreate,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """เพิ่มร้านค้าใหม่ — ต้องล็อกอินก่อน (สัปดาห์ 4)"""
    return crud.create_shop(session, data)
