"""Router สมัครสมาชิก/ล็อกอิน — สัปดาห์ 4

ใช้ OAuth2PasswordBearer/OAuth2PasswordRequestForm ตามมาตรฐานของ FastAPI เพื่อให้
Swagger UI (`/docs`) มีปุ่ม "Authorize" ทดสอบ endpoint ที่ต้องล็อกอินได้โดยตรง
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlmodel import Session

from app import crud, models, schemas
from app.auth import create_access_token, decode_access_token
from app.database import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

# tokenUrl ต้องตรงกับ path จริงของ endpoint login ด้านล่าง (รวม prefix /api ที่ main.py ใส่ให้)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@router.post("/register", response_model=schemas.UserRead, status_code=201)
def register(data: schemas.UserCreate, session: Session = Depends(get_session)):
    """สมัครสมาชิกใหม่ — Edge Case: อีเมลซ้ำจะได้ 400 พร้อมข้อความชัดเจน"""
    try:
        return crud.create_user(session, data)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """ล็อกอิน — ใช้ field `username` ส่งอีเมล (ตามมาตรฐาน OAuth2 form)
    Edge Case: อีเมล/รหัสผ่านผิดจะได้ 401 พร้อมข้อความชัดเจน ไม่บอกว่าผิดจุดไหน (กัน enumeration)
    """
    user = crud.authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(status_code=401, detail="อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    return schemas.Token(access_token=create_access_token(user.id))


def get_current_user(
    token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)
) -> models.User:
    """FastAPI dependency: ใช้ผูกกับ endpoint ที่ต้องล็อกอินก่อนถึงจะเรียกได้
    Edge Case: token ไม่มี/ผิด/หมดอายุ → 401 เสมอ
    """
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token ไม่ถูกต้องหรือหมดอายุ")
    user = session.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="ไม่พบผู้ใช้นี้")
    return user


@router.get("/me", response_model=schemas.UserRead)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    """คืนข้อมูลผู้ใช้ที่ล็อกอินอยู่ — ใช้ทดสอบว่า token ที่ได้ใช้งานได้จริง"""
    return current_user
