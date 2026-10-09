"""เปรียบเทียบสินค้า (เฟส 2): ตารางสเปกจัดกลุ่ม + ค่าที่ดีกว่าต่อแถว + ค่าส่ง/ราคารวม + ป้าย + สรุป 1 บรรทัด

หลัก 4 ข้อจาก Baymard: ซ่อนสเปกที่เหมือนกัน (diff_only), จัดกลุ่ม, หัวตารางติดจอ (frontend), แถวสลับสี (frontend)
ทุกตัวเลขในสรุปมาจากตารางเดียวกันนี้ ไม่คำนวณแยก
"""
import hashlib
import json
import re
from typing import List, Optional

from sqlmodel import Session, select

from app import models, pricing, shipping, specs

MAX_ITEMS = 4


def _short(name: str, n: int = 28) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def _unique_best(values: List[Optional[float]], better: str) -> Optional[int]:
    """index ของค่าที่ดีที่สุดแบบไม่เสมอ (ต้องมีค่าอย่างน้อย 2 ตัว) — None ถ้าเสมอ/เทียบไม่ได้"""
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(present) < 2 or better not in ("higher", "lower"):
        return None
    pick = max if better == "higher" else min
    best = pick(v for _, v in present)
    winners = [i for i, v in present if v == best]
    return winners[0] if len(winners) == 1 else None


def _rule_summary(items: List[dict], groups: List[dict], spec_best: List[tuple]) -> Optional[str]:
    """สรุปแบบกฎ (ไม่ใช้ AI): ราคารวมที่ถูกที่สุด + สเปกเด่นไม่เกิน 2 แถว ตัวเลขดึงจากตาราง"""
    if len(items) < 2:
        return None
    parts = []
    totals = [it["total"] for it in items]
    i = _unique_best([float(t) for t in totals], "lower")
    if i is not None:
        others = sorted(t for j, t in enumerate(totals) if j != i)
        diff = others[0] - totals[i]
        parts.append(
            f"{_short(items[i]['name'])} ถูกที่สุดเมื่อรวมค่าส่ง (฿{totals[i]:,}"
            + (f" ถูกกว่าอันดับถัดไป ฿{diff:,})" if diff > 0 else ")")
        )
    by_item: dict = {}
    for idx, label, disp in spec_best:
        by_item.setdefault(idx, []).append(f"{label} ({disp})")
    shown = 0
    for idx, feats in by_item.items():
        if shown >= 2:
            break
        feats = feats[: 2 - shown]
        shown += len(feats)
        parts.append(f"{_short(items[idx]['name'])} " + " และ".join(feats))
    return " · ".join(parts) or None


def _fingerprint(items: List[dict], groups: List[dict]) -> str:
    data = [[it["product_id"], it["price"], it["total"], it["rating"], it["review_count"]] for it in items]
    cells = [[r["key"], [c["display"] for c in r["cells"]]] for g in groups for r in g["rows"]]
    return hashlib.sha1(json.dumps([data, cells], ensure_ascii=False).encode()).hexdigest()


def _cached_summary(session: Session, ids: List[int], province: Optional[str], fp: str, make) -> Optional[str]:
    """สรุปต่อชุดสินค้า+จังหวัด cache ไว้ใน compare_summary สร้างใหม่เมื่อข้อมูลที่ใช้เปลี่ยน"""
    key = hashlib.sha1(f"{sorted(ids)}|{province or ''}".encode()).hexdigest()
    row = session.get(models.CompareSummary, key)
    if row is not None and row.fingerprint == fp:
        return row.summary or None
    summary = make() or ""
    if row is None:
        row = models.CompareSummary(sku_set_hash=key, fingerprint=fp, summary=summary)
    else:
        row.fingerprint, row.summary = fp, summary
        row.created_at = pricing.utcnow_naive()
    session.add(row)
    session.commit()
    return summary or None


def parse_ids(raw: str) -> List[int]:
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise ValueError("ids ต้องเป็นตัวเลขคั่นด้วยจุลภาค")
    ids = list(dict.fromkeys(ids))  # ตัดซ้ำ คงลำดับ
    if not 1 <= len(ids) <= MAX_ITEMS:
        raise ValueError(f"เทียบได้ 1–{MAX_ITEMS} ชิ้น")
    return ids


def compare(session: Session, ids: List[int], province: Optional[str] = None,
            diff_only: bool = True, summarizer=None) -> dict:
    province = shipping.normalize_province(province)
    products, missing = [], []
    for pid in ids:
        p = session.get(models.Product, pid)
        (products.append(p) if p is not None and p.is_active else missing.append(pid))

    cat_ids = {p.category_id for p in products}
    same_category = bool(products) and len(cat_ids) == 1 and None not in cat_ids

    items = []
    for p in products:
        disp = pricing.compute_display(p)
        q = shipping.quote(session, p.shop_id, [(p, 1)], province)
        items.append(dict(
            product_id=p.id, name=p.name, image=p.image, cover_url=p.cover_url,
            price=p.price, original_price=disp.ref_price, discount_percent=disp.shown_percent,
            rating=round(p.rating, 2), review_count=p.review_count,
            shop_id=p.shop_id, shop_name=p.shop.name if p.shop else "",
            shop_rating=round(p.shop.rating, 2) if p.shop else 0.0,
            stock=p.stock, spec_complete=specs.is_complete(session, p), category_id=p.category_id,
            shipping={k: q[k] for k in ("fee", "days_min", "days_max", "free_reason", "free_over")},
            total=p.price + q["fee"], badges=[],
        ))

    # ---- ตารางสเปก (เฉพาะหมวดเดียวกัน)
    groups: List[dict] = []
    spec_best: List[tuple] = []
    if same_category:
        vals = [specs.values_of(session, p.id) for p in products]
        by_group: dict = {}
        for a in specs.template(session, products[0].category_id):
            cells, ranks = [], []
            for v in vals:
                pv = v.get(a.key)
                vn, vt = (pv.value_num, pv.value_text) if pv else (None, None)
                cells.append({"display": specs.display(a, vn, vt), "is_best": False})
                ranks.append(specs.rank(a, vn, vt) if pv else None)
            if all(c["display"] is None for c in cells):
                continue  # ไม่มีร้านไหนระบุเลย ไม่ต้องแสดงแถว
            differs = len({c["display"] for c in cells}) > 1
            best = _unique_best(ranks, a.better) if differs else None
            if best is not None:
                cells[best]["is_best"] = True
                if a.badge_label:
                    items[best]["badges"].append(a.badge_label)
                spec_best.append((best, a.badge_label or f"{a.name_th}ดีที่สุด", cells[best]["display"]))
            if diff_only and not differs:
                continue
            by_group.setdefault(a.group_name, []).append(dict(
                key=a.key, name_th=a.name_th, unit=a.unit, better=a.better, differs=differs, cells=cells,
            ))
        groups = [{"name": g, "rows": rows} for g, rows in by_group.items()]

    # ---- ป้ายราคา/รีวิว
    if len(items) >= 2:
        # ต่างหมวด = ไม่ใช่ของทดแทนกัน → บอกว่า "ถูกที่สุด" ไม่มีความหมาย (เสื้อถูกกว่าหูฟัง)
        i = _unique_best([float(it["total"]) for it in items], "lower") if same_category else None
        if i is not None:
            items[i]["badges"].insert(0, "ถูกที่สุด (รวมค่าส่ง)")
        ratings = [it["rating"] if it["review_count"] > 0 else None for it in items]
        i = _unique_best(ratings, "higher")
        if i is not None:
            items[i]["badges"].insert(1 if items[i]["badges"][:1] == ["ถูกที่สุด (รวมค่าส่ง)"] else 0, "รีวิวดีที่สุด")

    if not same_category and len(items) >= 2:
        summary = "สินค้าต่างประเภทกัน เทียบได้แค่ราคา ค่าส่ง และรีวิว"
        return dict(
            province=province, region=shipping.region_of(province), same_category=False,
            summary=summary, missing_ids=missing, items=items, groups=[],
        )

    fp = _fingerprint(items, groups)
    make = (lambda: summarizer(items, groups, spec_best)) if summarizer else (
        lambda: _rule_summary(items, groups, spec_best))
    summary = _cached_summary(session, [it["product_id"] for it in items], province, fp, make) if items else None

    return dict(
        province=province, region=shipping.region_of(province), same_category=same_category,
        summary=summary, missing_ids=missing, items=items, groups=groups,
    )


# ---------------------------------------------------------------- ร้านอื่นที่ขายรุ่นนี้

def _norm(s: Optional[str]) -> str:
    return re.sub(r"[\s\-_/.]+", "", (s or "").casefold())


def same_model(session: Session, product: models.Product, province: Optional[str] = None) -> List[dict]:
    """ร้านอื่นที่ขายรุ่นเดียวกัน: บาร์โค้ดตรงกัน หรือ แบรนด์+รหัสรุ่นตรงกันทุกตัว (ไม่สนตัวพิมพ์/ช่องว่าง)"""
    province = shipping.normalize_province(province)
    barcode = (product.barcode or "").strip()
    brand, model_code = _norm(product.brand), _norm(product.model_code)
    if not barcode and not (brand and model_code):
        return []
    rows = []
    for p in session.exec(select(models.Product).where(
        models.Product.is_active == True, models.Product.id != product.id  # noqa: E712
    )).all():
        if p.shop_id == product.shop_id:
            continue
        if barcode and (p.barcode or "").strip() == barcode:
            match = "barcode"
        elif brand and model_code and _norm(p.brand) == brand and _norm(p.model_code) == model_code:
            match = "brand_model"
        else:
            continue
        q = shipping.quote(session, p.shop_id, [(p, 1)], province)
        rows.append(dict(
            product_id=p.id, shop_id=p.shop_id, shop_name=p.shop.name if p.shop else "",
            shop_rating=round(p.shop.rating, 2) if p.shop else 0.0, price=p.price,
            shipping_fee=q["fee"], total=p.price + q["fee"],
            days_min=q["days_min"], days_max=q["days_max"], match=match,
            free_reason=q["free_reason"], free_over=q["free_over"],
        ))
    rows.sort(key=lambda r: (r["total"], r["product_id"]))
    return rows


def similar(session: Session, product: models.Product, limit: int = 3) -> List[models.Product]:
    """สินค้าหมวดเดียวกันที่ราคาใกล้เคียงที่สุด (ปุ่ม "เทียบกับสินค้าคล้ายกัน")"""
    if product.category_id is None:
        return []
    others = session.exec(select(models.Product).where(
        models.Product.is_active == True,  # noqa: E712
        models.Product.category_id == product.category_id,
        models.Product.id != product.id,
    )).all()
    others = sorted(others, key=lambda p: (abs(p.price - product.price), p.id))
    return others[: max(0, min(limit, 10))]
