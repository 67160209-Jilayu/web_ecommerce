"""Router ฝั่งผู้ขาย — dashboard ราคา (เฟส 1)

แสดงราคาก่อนลดที่ระบบจะใช้, คำเตือนขึ้นราคาก่อนลด (พร้อมเหตุผลและวันที่), และจำนวนตะกร้า
ที่ถือสินค้าอยู่ (ไม่เปิดเผยตัวผู้ซื้อ) — ไม่ส่งประวัติราคาดิบออกไป
"""
from fastapi import APIRouter, Depends
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.shops import require_own_shop

router = APIRouter(prefix="/seller", tags=["seller"])


@router.get("/price-status", response_model=schemas.PriceStatus)
def price_status(
    session: Session = Depends(get_session),
    shop: models.Shop = Depends(require_own_shop),
):
    """สถานะราคาของทุกสินค้าในร้านฉัน"""
    return crud.seller_price_status(session, shop)
