"""ค้นหาตามความหมาย (เฟส 4) — เช่น "ของขวัญให้แม่" เจอสินค้าที่เหมาะ แม้ชื่อไม่มีคำนี้

- เก็บเวกเตอร์ในตาราง product_embedding (DB เดิม ไม่มีเซิร์ฟเวอร์เพิ่ม) คำนวณ cosine ใน Python
  (ขนาดข้อมูลตอนนี้เล็ก — ไม่ใช้ pgvector เพื่อไม่ต้องพึ่ง extension)
- embed เฉพาะข้อมูลสินค้า (ชื่อ แบรนด์ รุ่น หมวด สเปก คำอธิบาย) ไม่มีข้อมูลผู้ใช้
- embed หลัง commit เมื่อข้อความสินค้าเปลี่ยน + งาน backfill: python -m app.semantic
- ใช้แบบผสม: ผลค้นหาด้วยคำเหมือนเดิมทุกอย่าง แล้วต่อท้ายด้วยสินค้าที่ความหมายใกล้เคียง
- ปิดสวิตช์ / ไม่มีผู้ให้บริการ / ผิดพลาดใดๆ → ผลค้นหาเดิม ไม่เคย error
"""
import hashlib
import json
import math
from collections import OrderedDict
from typing import List, Optional

from sqlmodel import Session, select

from app import config, llm, models, settings, specs

_QUERY_CACHE: "OrderedDict[str, List[float]]" = OrderedDict()
_QUERY_CACHE_MAX = 512


def enabled(session: Session) -> bool:
    try:
        return bool(settings.get(session, "semantic_search")) and llm.get_adapter() is not None
    except Exception:  # noqa: BLE001
        return False


def model_name(adapter: llm.LlmAdapter) -> str:
    return f"{adapter.name}:{config.LLM_EMBED_MODEL if adapter.name == 'gemini' else 'local'}"


def product_text(session: Session, p: models.Product) -> str:
    parts = [p.name, p.brand or "", p.model_code or "", p.category.name if p.category else ""]
    parts += [f"{a['name_th']} {a['display']}" for a in specs.attribute_reads(session, p) if a["display"]]
    parts.append((p.description or "")[:1000])
    return "\n".join(x for x in parts if x)


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def embed_products(session: Session, products: List[models.Product],
                   adapter: Optional[llm.LlmAdapter] = None, force: bool = False) -> int:
    """embed เฉพาะสินค้าที่ข้อความเปลี่ยน (หรือ model เปลี่ยน) — ไม่ commit; คืนจำนวนที่ embed"""
    adapter = adapter or llm.get_adapter()
    if adapter is None or not products:
        return 0
    mname = model_name(adapter)
    todo, texts = [], []
    for p in products:
        text = product_text(session, p)
        row = session.get(models.ProductEmbedding, p.id)
        if not force and row is not None and row.text_hash == _hash(text) and row.model == mname:
            continue
        todo.append((p, text, row))
        texts.append(text)
    done = 0
    for i in range(0, len(todo), 50):
        chunk = todo[i:i + 50]
        vectors = adapter.embed([t for _, t, _ in chunk])
        for (p, text, row), vec in zip(chunk, vectors):
            if not vec:
                continue
            row = row or models.ProductEmbedding(product_id=p.id, model=mname, vector_json="[]", text_hash="")
            row.model, row.vector_json, row.text_hash = mname, json.dumps(vec), _hash(text)
            session.add(row)
            done += 1
    return done


def after_product_change(session: Session, product_id: int) -> None:
    """เรียกหลัง commit ที่สร้าง/แก้สินค้า — ผิดพลาดแล้วเงียบ (งาน backfill จะทำให้ภายหลัง)"""
    try:
        if not enabled(session):
            return
        p = session.get(models.Product, product_id)
        if p is not None and embed_products(session, [p]):
            session.commit()
    except Exception as err:  # noqa: BLE001
        session.rollback()
        print(f"[semantic] embed สินค้า {product_id} ไม่สำเร็จ: {err!r}", flush=True)


def backfill(session: Session) -> int:
    """embed สินค้าที่เปิดขายทั้งหมดที่ยังไม่มี/ข้อความเปลี่ยน (ไม่สนสวิตช์ — ใช้เตรียมก่อนเปิด)"""
    adapter = llm.get_adapter()
    if adapter is None:
        return 0
    products = session.exec(select(models.Product).where(models.Product.is_active == True)).all()  # noqa: E712
    n = embed_products(session, list(products), adapter)
    session.commit()
    return n


def _query_vector(adapter: llm.LlmAdapter, query: str) -> List[float]:
    key = f"{model_name(adapter)}|{query.strip().casefold()}"
    if key in _QUERY_CACHE:
        _QUERY_CACHE.move_to_end(key)
        return _QUERY_CACHE[key]
    vec = adapter.embed([query])[0]
    _QUERY_CACHE[key] = vec
    if len(_QUERY_CACHE) > _QUERY_CACHE_MAX:
        _QUERY_CACHE.popitem(last=False)
    return vec


def semantic_ids(session: Session, query: str, candidates: List[models.Product],
                 exclude: set) -> List[int]:
    """id สินค้าที่ความหมายใกล้คำค้น (จากชุด candidates ที่ผ่านตัวกรองแล้ว) เรียงจากใกล้สุด
    ผิดพลาดใดๆ → [] (ผู้เรียกใช้ผลค้นหาเดิม)"""
    try:
        if not query or not query.strip() or not enabled(session):
            return []
        adapter = llm.get_adapter()
        mname = model_name(adapter)
        qv = _query_vector(adapter, query)
        pool = [p for p in candidates if p.id not in exclude]
        if not pool:
            return []
        rows = {r.product_id: r for r in session.exec(select(models.ProductEmbedding).where(
            models.ProductEmbedding.product_id.in_([p.id for p in pool]))).all()}
        scored = []
        for p in pool:
            r = rows.get(p.id)
            if r is None or r.model != mname:
                continue
            s = cosine(qv, json.loads(r.vector_json))
            if s >= config.SEMANTIC_MIN_SCORE:
                scored.append((s, p.id))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [pid for _, pid in scored[: config.SEMANTIC_MAX_RESULTS]]
    except Exception as err:  # noqa: BLE001
        print(f"[semantic] ค้นหาตามความหมายไม่สำเร็จ ใช้ผลค้นหาปกติแทน: {err!r}", flush=True)
        return []


if __name__ == "__main__":  # python -m app.semantic
    from app.database import create_db_and_tables, engine

    create_db_and_tables()
    with Session(engine) as s:
        print({"embedded": backfill(s)})
