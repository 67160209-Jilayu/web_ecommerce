"""Router แชทช่วยช้อป (เฟส 3) — POST /api/chat ส่งเป็น Server-Sent Events

ลำดับ event: meta → cards (การ์ดสินค้าราคาสดจาก DB ส่งก่อน) → delta* (ข้อความที่ตรวจแล้ว) → done
ข้อผิดพลาดก่อนเริ่ม stream ตอบเป็น JSON ธรรมดา: 422 (ข้อความว่าง/ยาว), 429 (โควตา), 503 (ปิดแชท)
ทุกกรณีที่ใช้แชทไม่ได้ มี fallback=true ให้หน้าเว็บสลับเป็นโหมดปุ่มเลือก (GET /api/chat/guided)
"""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlmodel import Session, SQLModel, select

from app import chat, chat_guard, config, models
from app.database import engine, get_session
from app.routers.auth import get_optional_user

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(SQLModel):
    message: str
    session_id: Optional[str] = None
    context_sku_id: Optional[int] = None
    device_id: Optional[str] = None


class FeedbackIn(SQLModel):
    message_id: int
    value: Optional[str] = None    # up | down | null (ยกเลิก)
    device_id: Optional[str] = None


def _client_key(request: Request, device_id: Optional[str]) -> str:
    ip = request.client.host if request.client else ""
    return chat.client_key_of(ip, (device_id or "")[:64])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.get("/config")
def chat_config(
    device_id: Optional[str] = Query(None),
    context: str = Query("home", description="home | product | compare (เลือกคำถามตัวอย่างให้เหมาะกับหน้า)"),
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """ข้อมูลที่หน้าแชทต้องใช้: เปิดให้ผู้ใช้นี้ไหม, ข้อความเตือนใต้ช่องพิมพ์, คำถามตัวอย่าง"""
    return {
        "enabled": chat.chat_enabled(session, current_user, device_id),
        "disclaimer": chat_guard.DISCLAIMER,
        "sample_questions": chat.sample_questions(session, context),
        "max_chars": config.CHAT_MAX_CHARS,
    }


@router.post("")
def post_chat(
    data: ChatRequest,
    request: Request,
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """ส่งข้อความถึงผู้ช่วย — ตอบเป็น text/event-stream"""
    if not chat.chat_enabled(session, current_user, data.device_id):
        return JSONResponse(status_code=503, content={
            "detail": "ผู้ช่วยแชทยังไม่เปิดให้ใช้ตอนนี้ ใช้ปุ่มเลือกสินค้าแทนได้เลยครับ", "fallback": True})
    chk = chat_guard.check_input(data.message)
    if not chk.ok:
        raise HTTPException(status_code=422, detail=chk.error)
    key = _client_key(request, data.device_id)
    limited = chat.check_limits(session, current_user, key)
    if limited:
        return JSONResponse(status_code=429, headers={"Retry-After": str(limited["retry_after"])},
                            content={**limited, "fallback": True})

    user_id = current_user.id if current_user else None

    def stream():
        # session ของตัวเอง เพราะ dependency session ถูกปิดก่อน stream จบ
        with Session(engine) as s:
            user = s.get(models.User, user_id) if user_id else None
            try:
                for event, payload in chat.iter_answer(
                    s, data.message, session_id=data.session_id, context_sku_id=data.context_sku_id,
                    user=user, client_key=key,
                ):
                    yield _sse(event, payload)
            except chat.ChatRejected as err:
                yield _sse("error", {"detail": str(err)})
            except Exception:  # noqa: BLE001 — ไม่ส่งรายละเอียดภายในออกไป
                s.rollback()
                yield _sse("done", {"message_id": None, "text": "", "suggestions": [], "links": [],
                                    "note": None, "fallback": True})

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/feedback", status_code=204)
def feedback(
    data: FeedbackIn,
    request: Request,
    session: Session = Depends(get_session),
    current_user: Optional[models.User] = Depends(get_optional_user),
):
    """👍/👎 ต่อคำตอบ (เก็บไว้ทำชุดทดสอบ) — ได้เฉพาะเจ้าของบทสนทนา"""
    if data.value not in ("up", "down", None):
        raise HTTPException(status_code=422, detail="value ต้องเป็น up หรือ down")
    msg = session.get(models.ChatMessage, data.message_id)
    owner = msg is not None and msg.role == "model" and (
        (current_user is not None and msg.user_id == current_user.id)
        or (msg.user_id is None and msg.client_key == _client_key(request, data.device_id))
    )
    if not owner:
        raise HTTPException(status_code=404, detail="ไม่พบคำตอบนี้")
    msg.feedback = data.value
    session.add(msg)
    session.commit()
    return Response(status_code=204)


@router.get("/guided")
def guided(
    category_id: Optional[int] = Query(None),
    max_price: Optional[str] = Query(None, description="ตัวเลข หรือ any = ไม่จำกัด"),
    use: Optional[str] = Query(None, description="ค่าการใช้งาน หรือว่าง = ไม่ระบุ"),
    session: Session = Depends(get_session),
):
    """โหมดปุ่มเลือก (ไม่ใช้ AI): หมวด → งบ → การใช้งาน → ผลลัพธ์ — ใช้ตอน AI ใช้ไม่ได้ และเป็นโหมดง่ายสำหรับคนไม่อยากพิมพ์"""
    if max_price is not None and max_price != "any" and not max_price.isdigit():
        raise HTTPException(status_code=422, detail="งบประมาณต้องเป็นตัวเลข")
    return chat.guided(session, category_id, max_price, use)
