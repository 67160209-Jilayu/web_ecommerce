"""จับคู่ "อาจเป็นรุ่นเดียวกัน" แบบไม่ตรงทุกตัว (เฟส 4) — แยกจาก "ร้านอื่นที่ขายรุ่นนี้" (ตรงทุกตัว) เสมอ

คะแนน = น้ำหนักชื่อ × ความคล้ายของชื่อ + น้ำหนักแบรนด์ × แบรนด์ + น้ำหนักสเปก × สเปกที่ตรงกัน
- ชื่อมีน้ำหนักจำกัด (FUZZY_NAME_WEIGHT < threshold) → ผู้ขายยัดชื่อสินค้าคนอื่นอย่างเดียวไม่มีทางผ่าน
- ความคล้ายชื่อใช้ Jaccard ของ char-trigram: ยิ่งยัดคำมาก ยิ่งคล้ายน้อยลง
- ตัดทิ้งทันทีเมื่อมีหลักฐานว่าเป็นคนละรุ่น: บาร์โค้ดต่างกัน / แบรนด์ต่างกัน / แบรนด์+รหัสรุ่นต่างกัน
"""
import re
from typing import List, Optional, Tuple

from sqlmodel import Session, select

from app import compare, config, models, shipping, specs

LABEL = "อาจเป็นรุ่นเดียวกัน"
_SKIP_KEYS = {"color"}   # สีต่างกันยังเป็นรุ่นเดียวกันได้
# คำบอกระดับรุ่น/เลขรุ่น — ชื่อต่างกันที่คำเหล่านี้ = คนละรุ่น (Pro ≠ Max ≠ Mini, รุ่น 2 ≠ รุ่น 3)
_TIER_TOKENS = {"pro", "max", "mini", "lite", "plus", "ultra", "se", "air", "neo", "prime", "รุ่นเล็ก", "รุ่นใหญ่"}
# คำที่ตลาดไทยใช้เรียกของเลียนแบบ — ห้ามจับคู่กับสินค้าแบรนด์จริง ไม่ว่าฝั่งไหน
_KNOCKOFF = ("เกรดเอ", "เกรด a", "ก๊อป", "ก็อป", "เทียบแท้", "มิเรอร์", "mirror", "งานจีน",
             "copy", "replica", "fake", "ปลอม", "เลียนแบบ", "งานเทียบ")


def _tier_tokens(name: str) -> set:
    t = (name or "").casefold()
    toks = {w for w in re.sub(r"[^\w฀-๿]+", " ", t).split() if w in _TIER_TOKENS}
    toks |= {w for w in ("รุ่นเล็ก", "รุ่นใหญ่") if w in t}
    toks |= set(re.findall(r"(?<![\d.,])\d{1,2}(?![\d.,])", t))   # เลขรุ่น 1–2 หลัก เช่น 2 / 3 / 15
    return toks


# "AAA" เป็นทั้งเกรดของปลอม ("เกรด AAA") และขนาดถ่าน ("ใช้ถ่าน AAA") — นับเป็นของเลียนแบบเฉพาะบริบทที่ไม่ใช่ถ่าน
_AAA_BATTERY = re.compile(r"(ถ่าน|แบต|battery|batteries|size|ไซส์|ขนาด|ใช้)\s*(aaa|aa)|aaa\s*(battery|batteries|ก้อน|x\s*\d)")
_AAA_GRADE = re.compile(r"(เกรด|grade|งาน)\s*aaa|aaa\s*(grade|เกรด|งาน)|aaa\s*$|aaa\s+(ราคา|ถูก|ขายส่ง)")


def is_knockoff(name_or_text: str) -> bool:
    low = (name_or_text or "").casefold()
    if any(k in low for k in _KNOCKOFF):
        return True
    return bool(_AAA_GRADE.search(low)) and not _AAA_BATTERY.search(low)


def _spec_conflict(session: Session, a: models.Product, b: models.Product) -> bool:
    """สเปกตัวเลขที่ทั้งสองฝั่งระบุต่างกันเกิน 10% = ไม่ใช่รุ่นเดียวกัน (เช่น แบต 20 ชม. vs 5 ชม.)"""
    va, vb = specs.values_of(session, a.id), specs.values_of(session, b.id)
    for k, x in va.items():
        y = vb.get(k)
        if y is None or k in _SKIP_KEYS or x.value_num is None or y.value_num is None:
            continue
        hi = max(abs(x.value_num), abs(y.value_num)) or 1.0
        if abs(x.value_num - y.value_num) / hi > 0.10:
            return True
    return False


def _norm_name(name: str) -> str:
    t = (name or "").casefold()
    t = re.sub(r"[^\w฀-๿]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _trigrams(t: str) -> set:
    t = f"  {t} "
    return {t[i:i + 3] for i in range(len(t) - 2)}


def name_similarity(a: str, b: str) -> float:
    ta, tb = _trigrams(_norm_name(a)), _trigrams(_norm_name(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _spec_agreement(session: Session, a: models.Product, b: models.Product) -> Tuple[float, int, int]:
    """(สัดส่วนที่ตรง, จำนวนที่ตรง, จำนวนที่มีทั้งสองฝั่ง) — ต้องมีร่วมกัน ≥ 2 ข้อถึงนับ"""
    va, vb = specs.values_of(session, a.id), specs.values_of(session, b.id)
    shared = [k for k in va if k in vb and k not in _SKIP_KEYS]
    if len(shared) < 2:
        return 0.0, 0, len(shared)
    same = 0
    for k in shared:
        x, y = va[k], vb[k]
        if x.value_num is not None and y.value_num is not None:
            hi = max(abs(x.value_num), abs(y.value_num)) or 1.0
            same += abs(x.value_num - y.value_num) / hi <= 0.02
        else:
            same += (x.value_text or "").strip().casefold() == (y.value_text or "").strip().casefold()
    return same / len(shared), same, len(shared)


def score_pair(a: models.Product, b: models.Product, session: Session) -> Optional[Tuple[float, List[str]]]:
    """(คะแนน 0–1, เหตุผลสั้นๆ) หรือ None ถ้ามีหลักฐานว่าเป็นคนละรุ่น"""
    if a.barcode and b.barcode and a.barcode.strip() != b.barcode.strip():
        return None
    ba, bb = compare._norm(a.brand), compare._norm(b.brand)
    if ba and bb and ba != bb:
        return None
    ma, mb = compare._norm(a.model_code), compare._norm(b.model_code)
    if ba and bb and ma and mb and ma != mb:
        return None
    if is_knockoff(a.name) or is_knockoff(b.name) or is_knockoff(a.description) or is_knockoff(b.description):
        return None
    if _tier_tokens(a.name) != _tier_tokens(b.name):
        return None   # Pro vs Max, 2 vs 3 ฯลฯ = คนละรุ่น
    if _spec_conflict(session, a, b):
        return None

    reasons = []
    name = name_similarity(a.name, b.name)
    if name >= 0.5:
        reasons.append("ชื่อคล้ายกัน")
    if ba and bb:
        brand = 1.0
        reasons.append("แบรนด์เดียวกัน")
    else:
        brand = 0.0   # ต้องระบุแบรนด์ทั้งสองฝั่ง (ชื่อที่มีคำแบรนด์ไม่นับ)
    spec, same, _shared = _spec_agreement(session, a, b)
    if same:
        reasons.append(f"สเปกตรงกัน {same} ข้อ")
    score = (config.FUZZY_NAME_WEIGHT * name + config.FUZZY_BRAND_WEIGHT * brand
             + config.FUZZY_SPEC_WEIGHT * spec)
    return round(score, 3), reasons


def maybe_same(session: Session, product: models.Product, province: Optional[str] = None) -> List[dict]:
    """สินค้าร้านอื่นที่ "อาจเป็นรุ่นเดียวกัน" — ไม่รวมรายการที่จับคู่ตรงทุกตัวแล้ว"""
    if product.category_id is None:
        return []
    province = shipping.normalize_province(province)
    exact = {r["product_id"] for r in compare.same_model(session, product, province)}
    cands = session.exec(select(models.Product).where(
        models.Product.is_active == True,  # noqa: E712
        models.Product.category_id == product.category_id,
        models.Product.id != product.id,
    )).all()
    rows = []
    for p in cands:
        if p.shop_id == product.shop_id or p.id in exact:
            continue
        if not (0.5 * product.price <= p.price <= 2 * product.price):
            continue
        res = score_pair(product, p, session)
        if res is None or res[0] < config.FUZZY_MATCH_THRESHOLD:
            continue
        q = shipping.quote(session, p.shop_id, [(p, 1)], province)
        rows.append(dict(
            product_id=p.id, name=p.name, image=p.image, cover_url=p.cover_url,
            shop_id=p.shop_id, shop_name=p.shop.name if p.shop else "",
            shop_rating=round(p.shop.rating, 2) if p.shop else 0.0, price=p.price,
            shipping_fee=q["fee"], total=p.price + q["fee"], days_min=q["days_min"], days_max=q["days_max"],
            free_reason=q["free_reason"], free_over=q["free_over"],
            score=res[0], reasons=res[1], label=LABEL,
        ))
    rows.sort(key=lambda r: (-r["score"], r["total"], r["product_id"]))
    top = rows[: config.FUZZY_MAX_RESULTS]
    return sorted(top, key=lambda r: (r["total"], r["product_id"]))
