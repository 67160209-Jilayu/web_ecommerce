"""Router ข้อมูลค่าส่ง: รายชื่อจังหวัด/ภาค (ใช้ทำตัวเลือกจังหวัด)"""
from fastapi import APIRouter

from app import schemas, shipping

router = APIRouter(prefix="/shipping", tags=["shipping"])


@router.get("/provinces", response_model=list[schemas.ProvinceRead])
def list_provinces():
    """77 จังหวัดพร้อมภาค"""
    return [schemas.ProvinceRead(name=n, region=r) for n, r in shipping.PROVINCES]


@router.get("/regions", response_model=list[str])
def list_regions():
    """ภาคที่ร้านตั้งค่าส่งเฉพาะได้"""
    return shipping.REGIONS
