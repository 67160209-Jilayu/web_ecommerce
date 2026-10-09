"""Router เปรียบเทียบสินค้า (เฟส 2) — ตาราง 2–4 ชิ้น ลิงก์แชร์ได้ /pages/compare.html?ids=..."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app import compare, crud, models, schemas
from app.database import get_session
from app.routers.auth import get_optional_user

router = APIRouter(prefix="/compare", tags=["compare"])


@router.get("", response_model=schemas.CompareResult)
def compare_products(
    ids: str = Query(..., description="product id คั่นด้วยจุลภาค 1–4 ชิ้น"),
    diff_only: bool = Query(True, description="ซ่อนสเปกที่เหมือนกันทุกชิ้น"),
    province: Optional[str] = Query(None, description="จังหวัดผู้ซื้อ (ไม่ส่ง = ใช้ของบัญชี)"),
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """ตารางเทียบ: สเปกจัดกลุ่ม + ค่าที่ดีกว่าต่อแถว + ค่าส่ง/ราคารวม + ป้าย + สรุป 1 บรรทัด"""
    try:
        id_list = compare.parse_ids(ids)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
    if not province and current_user is not None:
        province = crud.get_account_province(session, current_user).province
    return compare.compare(session, id_list, province, diff_only)
