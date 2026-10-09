"""AI เสนอค่าสเปกจากคำอธิบายสินค้า (เฟส 2) — เก็บเป็น "ข้อเสนอ" ผู้ขายต้องกดยืนยันเอง

- งาน batch กลางคืน: `python -m app.spec_suggest` (เรียกครั้งเดียวต่อสินค้า ไม่เรียกซ้ำถ้าเคยเสนอแล้ว)
- ผู้ขายกด "ให้ AI ช่วยเติม" ได้วันละครั้งต่อสินค้า (generate_for_product)
- ผลจากโมเดลถูกตรวจกับแม่แบบเสมอ (key ต้องมีจริง, enum ต้องอยู่ในตัวเลือก, ตัวเลขต้องเป็นตัวเลข)
- ไม่มี LLM (ไม่มี key) → ไม่ทำอะไร คืนรายการว่าง
"""
import json
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlmodel import Session, select

from app import llm, models, specs

SYSTEM = (
    "คุณคือผู้ช่วยกรอกสเปกสินค้า อ่านคำอธิบายสินค้าแล้วดึงเฉพาะค่าที่ระบุไว้ชัดเจนในข้อความเท่านั้น "
    "ห้ามเดา ห้ามเติมค่าที่ไม่มีในข้อความ ตอบเป็น JSON รูปแบบ "
    '{"values":[{"key":"...","value_num":ตัวเลขหรือnull,"value_text":"..."หรือnull}]} '
    "ใช้ key และตัวเลือกจากแม่แบบที่ให้เท่านั้น ตัวเลขให้แปลงเป็นหน่วยตามแม่แบบ"
)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _template_payload(tmpl: List[models.CategoryAttribute]) -> list:
    return [
        {"key": a.key, "name_th": a.name_th, "unit": a.unit, "data_type": a.data_type,
         "options": specs.options_of(a)}
        for a in tmpl
    ]


@llm.fake_handler("spec_extract")
def _fake_extract(system: str, messages: list, ctx: dict) -> str:
    """ดึงแบบกฎตายตัว: ตัวเลข+หน่วยตามแม่แบบ และชื่อตัวเลือก enum ที่ปรากฏในคำอธิบาย"""
    text = ctx.get("description", "")
    out = []
    for a in ctx.get("template", []):
        if a["data_type"] == "number" and a["unit"]:
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*" + re.escape(a["unit"]), text, re.I)
            if m:
                out.append({"key": a["key"], "value_num": float(m.group(1).replace(",", ""))})
        elif a["data_type"] == "enum":
            for opt in a["options"] or []:
                if opt != "อื่นๆ" and opt.lower() in text.lower():
                    out.append({"key": a["key"], "value_text": opt})
                    break
    return json.dumps({"values": out}, ensure_ascii=False)


def _pending(session: Session, product_id: int) -> List[models.SpecSuggestion]:
    return list(session.exec(
        select(models.SpecSuggestion).where(
            models.SpecSuggestion.product_id == product_id,
            models.SpecSuggestion.status == "pending",
        ).order_by(models.SpecSuggestion.id)
    ).all())


def suggest_for_product(session: Session, product: models.Product,
                        adapter: Optional[llm.LlmAdapter] = None) -> List[models.SpecSuggestion]:
    """เรียก LLM 1 ครั้งสำหรับสินค้า 1 ชิ้น แล้วบันทึกข้อเสนอที่ผ่านการตรวจ (ไม่ commit)"""
    adapter = adapter or llm.get_adapter()
    tmpl = specs.template(session, product.category_id)
    if adapter is None or not tmpl or not (product.description or "").strip():
        return []
    filled = specs.values_of(session, product.id)
    todo = [a for a in tmpl if a.key not in filled]
    if not todo:
        return []
    ctx = {"description": f"{product.name}\n{product.description}", "template": _template_payload(todo)}
    prompt = (
        f"แม่แบบ: {json.dumps(ctx['template'], ensure_ascii=False)}\n"
        f"คำอธิบายสินค้า:\n{ctx['description'][:3000]}"
    )
    result = adapter.generate(SYSTEM, [{"role": "user", "text": prompt}],
                              task="spec_extract", context=ctx, json_mode=True, max_tokens=400)
    data = llm.parse_json(result.text) or {}
    raw = [v for v in data.get("values", []) if isinstance(v, dict)]

    # ลบข้อเสนอเก่าที่ยังค้าง แล้วใส่ชุดใหม่ (เฉพาะค่าที่ผ่านการตรวจทีละตัว)
    for old in _pending(session, product.id):
        session.delete(old)
    created = []
    todo_keys = {a.key for a in todo}
    for v in raw:
        if v.get("key") not in todo_keys:
            continue
        try:
            clean = specs.validate_values(session, product.category_id, [v])
        except ValueError:
            continue  # โมเดลตอบผิดแม่แบบ → ทิ้ง
        if clean:
            s = models.SpecSuggestion(product_id=product.id, **clean[0])
            session.add(s)
            created.append(s)
    return created


def generate_for_product(session: Session, product: models.Product) -> List[models.SpecSuggestion]:
    """ผู้ขายกดขอเอง: จำกัดวันละครั้งต่อสินค้า (PermissionError → 429)"""
    last = session.exec(
        select(models.SpecSuggestion)
        .where(models.SpecSuggestion.product_id == product.id)
        .order_by(models.SpecSuggestion.created_at.desc())
    ).first()
    if last is not None and _now() - specs_naive(last.created_at) < timedelta(hours=24):
        raise PermissionError("ขอให้ AI เสนอสเปกได้วันละครั้งต่อสินค้า ลองใหม่พรุ่งนี้")
    try:
        suggest_for_product(session, product)
    except llm.LlmUnavailable:
        return []
    session.commit()
    return _pending(session, product.id)


def specs_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def run(session: Session, limit: Optional[int] = None) -> int:
    """งาน batch: เสนอสเปกให้สินค้าที่ยังไม่เคยได้ข้อเสนอเลย คืนจำนวนข้อเสนอที่สร้าง"""
    adapter = llm.get_adapter()
    if adapter is None:
        return 0
    done = set(session.exec(select(models.SpecSuggestion.product_id).distinct()).all())
    products = session.exec(
        select(models.Product).where(models.Product.is_active == True)  # noqa: E712
    ).all()
    count = 0
    for i, p in enumerate(x for x in products if x.id not in done):
        if limit is not None and i >= limit:
            break
        try:
            count += len(suggest_for_product(session, p, adapter))
        except llm.LlmUnavailable as err:
            print(f"[spec_suggest] หยุด: {err}", flush=True)
            break
        session.commit()
    return count


if __name__ == "__main__":  # python -m app.spec_suggest (รันจากโฟลเดอร์ backend)
    from app.database import create_db_and_tables, engine

    create_db_and_tables()
    with Session(engine) as s:
        print({"suggestions": run(s)})
