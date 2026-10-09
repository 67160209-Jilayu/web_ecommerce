"""Router บัญชีผู้ใช้ — notice ราคาลดของสินค้าในตะกร้า (เฉพาะผู้ใช้ที่ล็อกอิน)

ไม่มี push/อีเมล/LINE: frontend ดึงไปแสดงเป็นแถบบนหน้าตะกร้า + จุดที่ไอคอนตะกร้า
แล้วเรียก PATCH /notices/read เมื่อผู้ใช้เห็นแล้ว (notice จะหายไป)
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/notices", response_model=schemas.NoticeList)
def list_notices(
    include_read: bool = Query(False, description="true = รวม notice ที่อ่านแล้วด้วย"),
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """notice ราคาลดของสินค้าในตะกร้าฉัน (ค่าเริ่มต้นเฉพาะที่ยังไม่อ่าน) + จำนวนที่ยังไม่อ่าน"""
    notices = crud.list_notices(session, current_user, include_read=include_read)
    unread = sum(1 for n in notices if n.read_at is None)
    return schemas.NoticeList(unread_count=unread, notices=notices)


@router.patch("/notices/read", status_code=204)
def mark_notices_read(
    data: Optional[schemas.NoticeMarkRead] = Body(None),
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ทำเครื่องหมายว่าอ่านแล้ว — body {ids:[...]} หรือไม่ส่ง/{} = ทุกอันที่ยังไม่อ่าน"""
    crud.mark_notices_read(session, current_user, data.ids if data else None)
    return Response(status_code=204)



@router.get("/province", response_model=schemas.AccountProvince)
def get_province(
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """จังหวัดของฉันสำหรับคิดค่าส่ง: ที่ตั้งไว้ในบัญชี → จังหวัดจากออเดอร์ล่าสุด → null"""
    return crud.get_account_province(session, current_user)


@router.put("/province", response_model=schemas.AccountProvince)
def set_province(
    data: schemas.ProvinceIn,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ตั้งจังหวัดหลักของบัญชี (null = ล้าง)"""
    try:
        return crud.set_account_province(session, current_user, data.province)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/compare-list", response_model=schemas.CompareIds)
def get_compare_list(
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """ถาดเปรียบเทียบที่บันทึกไว้ในบัญชี"""
    return crud.get_compare_list(session, current_user)


@router.put("/compare-list", response_model=schemas.CompareIds)
def set_compare_list(
    data: schemas.CompareIds,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """บันทึกถาดเปรียบเทียบ (สูงสุด 4 ชิ้น; id ที่ไม่มีอยู่จะถูกตัดทิ้ง)"""
    try:
        return crud.set_compare_list(session, current_user, data.ids)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err))
