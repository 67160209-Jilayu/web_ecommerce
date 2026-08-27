"""Router รีวิวสินค้า — รีวิวได้เฉพาะสินค้าที่ซื้อจริงและกดรับของแล้วเท่านั้น"""
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app import crud, models, schemas
from app.database import get_session
from app.routers.auth import get_current_user

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=schemas.ReviewRead, status_code=201)
def create_review(
    data: schemas.ReviewCreate,
    session: Session = Depends(get_session),
    current_user: models.User = Depends(get_current_user),
):
    """เขียนรีวิว 1 รายการสินค้าที่ซื้อ (1 รายการรีวิวได้ครั้งเดียว)

    เมื่อรีวิวสำเร็จ ระบบจะคำนวณคะแนนเฉลี่ยของสินค้าและร้านค้าใหม่ทันที
    """
    try:
        return crud.create_review(session, current_user, data)
    except LookupError as err:
        raise HTTPException(status_code=404, detail=str(err))
    except PermissionError as err:
        raise HTTPException(status_code=403, detail=str(err))
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
