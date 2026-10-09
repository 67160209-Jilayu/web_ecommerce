"""แม่แบบสเปกต่อหมวด + ตรวจค่าสเปกที่ผู้ขายกรอก + แสดงผล (เฟส 2)

หัวใจของทั้งการเทียบสินค้าและแชท: ชื่อสเปก/หน่วยต้องตรงกันทุกสินค้าในหมวด
ผู้ขายจึงกรอกได้เฉพาะ key ในแม่แบบ หน่วยล็อกไว้ และ enum ต้องเลือกจากตัวเลือกที่กำหนด
"""
import json
from typing import Dict, List, Optional

from sqlmodel import Session, select

from app import models

COLORS = ["ดำ", "ขาว", "เทา", "เงิน", "ทอง", "แดง", "ชมพู", "ส้ม", "เหลือง", "เขียว",
          "ฟ้า", "น้ำเงิน", "ม่วง", "น้ำตาล", "ครีม", "หลายสี", "อื่นๆ"]
WATER = ["ไม่กันน้ำ", "IPX4", "IPX5", "IPX7", "IP67", "IP68"]   # เรียงจากน้อย → มาก

# (key, name_th, unit, data_type, options, group, better, required, badge_label)
_T = tuple
TEMPLATES: Dict[str, List[_T]] = {
    "electronics": [
        ("device_type", "ประเภทอุปกรณ์", None, "enum",
         ["หูฟัง", "ลำโพง", "พาวเวอร์แบงก์", "สายชาร์จ/อะแดปเตอร์", "สมาร์ทวอทช์", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("connectivity", "การเชื่อมต่อ", None, "enum",
         ["ไม่มี", "มีสาย", "บลูทูธ", "บลูทูธ+มีสาย", "Wi-Fi"], "ทั่วไป", "none", True, None),
        ("battery_mah", "ความจุแบตเตอรี่", "mAh", "number", None, "แบตเตอรี่", "higher", False, "แบตจุที่สุด"),
        ("battery_hours", "ใช้งานต่อเนื่อง", "ชม.", "number", None, "แบตเตอรี่", "higher", False, "แบตอึดที่สุด"),
        ("charge_time_hours", "เวลาชาร์จเต็ม", "ชม.", "number", None, "แบตเตอรี่", "lower", False, "ชาร์จเร็วที่สุด"),
        ("charge_port", "พอร์ตชาร์จ", None, "enum",
         ["USB-C", "Micro-USB", "Lightning", "ชาร์จไร้สาย", "อื่นๆ"], "แบตเตอรี่", "none", False, None),
        ("water_resistance", "กันน้ำ", None, "enum", WATER, "ความทนทาน", "higher", False, "กันน้ำดีที่สุด"),
        ("weight_g", "น้ำหนัก", "g", "number", None, "ขนาด", "lower", False, "เบาที่สุด"),
        ("color", "สี", None, "enum", COLORS, "ขนาด", "none", False, None),
        ("warranty_months", "รับประกัน", "เดือน", "number", None, "การรับประกัน", "higher", True, "ประกันนานที่สุด"),
    ],
    "home": [
        ("item_type", "ประเภท", None, "enum",
         ["เครื่องนอน", "ของตกแต่ง", "จัดเก็บ", "ทำความสะอาด", "เฟอร์นิเจอร์", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("material", "วัสดุ", None, "enum",
         ["ผ้าฝ้าย", "โพลีเอสเตอร์", "ไม้", "พลาสติก", "โลหะ", "แก้ว", "เซรามิก", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("pieces", "จำนวนในชุด", "ชิ้น", "number", None, "ทั่วไป", "higher", False, "ได้จำนวนมากที่สุด"),
        ("width_cm", "กว้าง", "cm", "number", None, "ขนาด", "none", False, None),
        ("length_cm", "ยาว", "cm", "number", None, "ขนาด", "none", False, None),
        ("height_cm", "สูง", "cm", "number", None, "ขนาด", "none", False, None),
        ("capacity_l", "ความจุ", "ลิตร", "number", None, "ขนาด", "higher", False, "จุมากที่สุด"),
        ("weight_kg", "น้ำหนัก", "kg", "number", None, "ขนาด", "lower", False, "เบาที่สุด"),
        ("color", "สี", None, "enum", COLORS, "ขนาด", "none", False, None),
        ("warranty_months", "รับประกัน", "เดือน", "number", None, "การรับประกัน", "higher", False, "ประกันนานที่สุด"),
    ],
    "kitchen": [
        ("item_type", "ประเภท", None, "enum",
         ["หม้อ/กระทะ", "มีด/เขียง", "ภาชนะ", "เครื่องใช้ไฟฟ้าในครัว", "กล่องเก็บอาหาร", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("material", "วัสดุ", None, "enum",
         ["สแตนเลส", "อลูมิเนียม", "เหล็กหล่อ", "เซรามิก", "แก้ว", "พลาสติก BPA-free", "ไม้", "ซิลิโคน", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("capacity_l", "ความจุ", "ลิตร", "number", None, "ขนาด", "higher", False, "จุมากที่สุด"),
        ("diameter_cm", "เส้นผ่านศูนย์กลาง", "cm", "number", None, "ขนาด", "none", False, None),
        ("weight_kg", "น้ำหนัก", "kg", "number", None, "ขนาด", "lower", False, "เบาที่สุด"),
        ("power_w", "กำลังไฟ", "W", "number", None, "การใช้งาน", "none", False, None),
        ("nonstick", "เคลือบกันติด", None, "bool", None, "การใช้งาน", "higher", False, None),
        ("induction", "ใช้กับเตาแม่เหล็กไฟฟ้าได้", None, "bool", None, "การใช้งาน", "higher", False, None),
        ("dishwasher_safe", "เข้าเครื่องล้างจานได้", None, "bool", None, "การใช้งาน", "higher", False, None),
        ("warranty_months", "รับประกัน", "เดือน", "number", None, "การรับประกัน", "higher", False, "ประกันนานที่สุด"),
    ],
    "beauty": [
        ("product_type", "ประเภท", None, "enum",
         ["สกินแคร์", "เมคอัพ", "ดูแลผม", "ดูแลผิวกาย", "น้ำหอม", "อื่นๆ"], "ทั่วไป", "none", True, None),
        ("skin_type", "เหมาะกับสภาพผิว", None, "enum",
         ["ทุกสภาพผิว", "ผิวมัน", "ผิวแห้ง", "ผิวผสม", "ผิวแพ้ง่าย"], "ทั่วไป", "none", False, None),
        ("volume_ml", "ปริมาณ", "ml", "number", None, "ปริมาณ", "higher", False, "ปริมาณมากที่สุด"),
        ("spf", "ค่า SPF", None, "number", None, "คุณสมบัติ", "higher", False, "SPF สูงที่สุด"),
        ("fragrance_free", "ไม่มีน้ำหอม", None, "bool", None, "คุณสมบัติ", "none", False, None),
        ("shelf_life_months", "อายุหลังผลิต", "เดือน", "number", None, "คุณสมบัติ", "higher", False, None),
        ("country", "ประเทศผู้ผลิต", None, "enum",
         ["ไทย", "เกาหลี", "ญี่ปุ่น", "สหรัฐฯ", "ฝรั่งเศส", "จีน", "อื่นๆ"], "ข้อมูลผลิตภัณฑ์", "none", False, None),
        ("fda_number", "เลขที่จดแจ้ง อย.", None, "text", None, "ข้อมูลผลิตภัณฑ์", "none", True, None),
    ],
    "fashion": [
        ("item_type", "ประเภท", None, "enum",
         ["เสื้อ", "กางเกง", "กระโปรง", "ชุดเดรส", "รองเท้า", "กระเป๋า", "เครื่องประดับ", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("gender", "สำหรับ", None, "enum", ["ชาย", "หญิง", "Unisex", "เด็ก"], "ทั่วไป", "none", True, None),
        ("material", "เนื้อผ้า/วัสดุ", None, "enum",
         ["ผ้าฝ้าย", "โพลีเอสเตอร์", "ลินิน", "ยีนส์", "หนังแท้", "หนังเทียม", "ผ้าผสม", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("size", "ไซส์", None, "enum", ["XS", "S", "M", "L", "XL", "XXL", "ฟรีไซส์"], "ขนาด", "none", False, None),
        ("chest_cm", "รอบอก", "cm", "number", None, "ขนาด", "none", False, None),
        ("length_cm", "ความยาว", "cm", "number", None, "ขนาด", "none", False, None),
        ("weight_g", "น้ำหนัก", "g", "number", None, "ขนาด", "lower", False, "เบาที่สุด"),
        ("color", "สี", None, "enum", COLORS, "ขนาด", "none", False, None),
    ],
    "sports": [
        ("item_type", "ประเภท", None, "enum",
         ["อุปกรณ์ฟิตเนส", "เสื้อผ้ากีฬา", "รองเท้ากีฬา", "แคมป์ปิ้ง", "จักรยาน", "ลูกบอล/ไม้", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("material", "วัสดุ", None, "enum",
         ["โพลีเอสเตอร์", "ไนลอน", "ยาง", "เหล็ก", "อลูมิเนียม", "พลาสติก", "อื่นๆ"],
         "ทั่วไป", "none", True, None),
        ("max_load_kg", "รับน้ำหนักสูงสุด", "kg", "number", None, "สมรรถนะ", "higher", False, "รับน้ำหนักได้มากที่สุด"),
        ("water_resistance", "กันน้ำ", None, "enum", WATER, "สมรรถนะ", "higher", False, "กันน้ำดีที่สุด"),
        ("foldable", "พับเก็บได้", None, "bool", None, "สมรรถนะ", "higher", False, None),
        ("length_cm", "ความยาว", "cm", "number", None, "ขนาด", "none", False, None),
        ("weight_kg", "น้ำหนัก", "kg", "number", None, "ขนาด", "lower", False, "เบาที่สุด"),
        ("color", "สี", None, "enum", COLORS, "ขนาด", "none", False, None),
        ("warranty_months", "รับประกัน", "เดือน", "number", None, "การรับประกัน", "higher", False, "ประกันนานที่สุด"),
    ],
}


def seed_templates(session: Session) -> int:
    """upsert แม่แบบสเปกของทุกหมวด (ทำทุกครั้งตอน startup — แก้ TEMPLATES แล้วรีสตาร์ตได้เลย)"""
    changed = 0
    for slug, attrs in TEMPLATES.items():
        cat = session.exec(select(models.Category).where(models.Category.slug == slug)).first()
        if cat is None:
            continue
        existing = {
            a.key: a for a in session.exec(
                select(models.CategoryAttribute).where(models.CategoryAttribute.category_id == cat.id)
            ).all()
        }
        for i, (key, name, unit, dtype, options, group, better, required, badge) in enumerate(attrs):
            row = existing.get(key) or models.CategoryAttribute(category_id=cat.id, key=key, name_th=name)
            values = dict(
                name_th=name, unit=unit, data_type=dtype,
                options_json=json.dumps(options, ensure_ascii=False) if options else None,
                group_name=group, better=better, required=required, sort=i, badge_label=badge,
            )
            if row.id is None or any(getattr(row, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(row, k, v)
                session.add(row)
                changed += 1
    session.commit()
    return changed


def options_of(attr: models.CategoryAttribute) -> Optional[List[str]]:
    return json.loads(attr.options_json) if attr.options_json else None


def template(session: Session, category_id: Optional[int]) -> List[models.CategoryAttribute]:
    """แม่แบบสเปกของหมวด — cache ไว้ต่อ 1 request

    หน้ารายการสินค้าเรียกฟังก์ชันนี้ซ้ำทุกชิ้น ทั้งที่สินค้าหมวดเดียวกันได้ผลเหมือนกันเสมอ
    ถ้าไม่ cache จะกลายเป็น query ละหนึ่งรอบต่อสินค้าหนึ่งชิ้น ซึ่งช้ามากเมื่อฐานข้อมูลอยู่ไกล
    (session.info มีอายุเท่ากับ 1 request เพราะ get_session เปิด session ใหม่ทุกครั้ง)
    """
    if category_id is None:
        return []
    cache = session.info.setdefault("_spec_template_cache", {})
    if category_id not in cache:
        cache[category_id] = list(session.exec(
            select(models.CategoryAttribute)
            .where(models.CategoryAttribute.category_id == category_id)
            .order_by(models.CategoryAttribute.sort)
        ).all())
    return cache[category_id]


VALUES_CACHE_KEY = "_spec_values_cache"


def values_of(session: Session, product_id: int) -> Dict[str, models.ProductAttributeValue]:
    cached = session.info.get(VALUES_CACHE_KEY)
    if cached is not None and product_id in cached:
        return cached[product_id]
    return {
        v.key: v for v in session.exec(
            select(models.ProductAttributeValue).where(models.ProductAttributeValue.product_id == product_id)
        ).all()
    }


def prefetch_values(session: Session, product_ids: list) -> None:
    """ดึงค่าสเปกของสินค้าหลายชิ้นในรอบเดียว แล้วพักไว้ให้ values_of ใช้ต่อ

    หน้ารายการสินค้าเรียก values_of ทีละชิ้น ซึ่งกลายเป็น query ละรอบต่อสินค้าหนึ่งชิ้น
    cache อยู่บน session จึงมีอายุแค่ 1 request และถูกล้างทุกครั้งที่มีการแก้ค่าสเปก
    """
    if not product_ids:
        return
    bucket: Dict[int, Dict[str, models.ProductAttributeValue]] = {pid: {} for pid in product_ids}
    rows = session.exec(
        select(models.ProductAttributeValue).where(
            models.ProductAttributeValue.product_id.in_(product_ids)
        )
    ).all()
    for v in rows:
        bucket.setdefault(v.product_id, {})[v.key] = v
    session.info[VALUES_CACHE_KEY] = bucket


def clear_values_cache(session: Session) -> None:
    """ต้องเรียกหลังแก้ค่าสเปก ไม่งั้นผู้เรียกถัดไปในรอบเดียวกันจะได้ค่าเก่า"""
    session.info.pop(VALUES_CACHE_KEY, None)


def _fmt_num(x: float) -> str:
    return f"{int(x):,}" if float(x).is_integer() else f"{x:,.2f}".rstrip("0").rstrip(".")


def display(attr: models.CategoryAttribute, value_num: Optional[float], value_text: Optional[str]) -> Optional[str]:
    """ข้อความแสดงผล — None = ร้านไม่ได้ระบุ"""
    if attr.data_type == "number":
        if value_num is None:
            return None
        return _fmt_num(value_num) + (f" {attr.unit}" if attr.unit else "")
    if attr.data_type == "bool":
        if value_num is None:
            return None
        return "มี" if value_num else "ไม่มี"
    return value_text or None


def rank(attr: models.CategoryAttribute, value_num: Optional[float], value_text: Optional[str]) -> Optional[float]:
    """ค่าสำหรับเทียบ "ดีกว่า" (มากกว่า = ดีกว่าเมื่อ better=higher) — None = เทียบไม่ได้"""
    if attr.data_type in ("number", "bool"):
        return value_num
    if attr.data_type == "enum" and value_text is not None:
        opts = options_of(attr) or []
        if value_text in opts and value_text != "อื่นๆ":
            return float(opts.index(value_text))
    return None


def validate_values(
    session: Session, category_id: Optional[int], items: List[dict]
) -> List[dict]:
    """ตรวจค่าที่ผู้ขายส่งมา คืนรายการที่สะอาดแล้ว [{key, value_num, value_text}] หรือ raise ValueError (ไทย)"""
    tmpl = {a.key: a for a in template(session, category_id)}
    clean, seen = [], set()
    for raw in items:
        key = (raw.get("key") or "").strip()
        vnum, vtext = raw.get("value_num"), raw.get("value_text")
        if isinstance(vtext, str):
            vtext = vtext.strip() or None
        if vnum is None and vtext is None:
            continue  # ค่าว่าง = ไม่ระบุ
        attr = tmpl.get(key)
        if attr is None:
            raise ValueError(f"สเปก '{key}' ไม่อยู่ในแม่แบบของหมวดนี้")
        if key in seen:
            raise ValueError(f"สเปก '{attr.name_th}' ส่งมาซ้ำ")
        seen.add(key)
        if attr.data_type == "number":
            try:
                vnum = float(vnum if vnum is not None else vtext)
            except (TypeError, ValueError):
                raise ValueError(f"'{attr.name_th}' ต้องเป็นตัวเลข")
            if vnum < 0 or vnum != vnum or vnum > 1e9:
                raise ValueError(f"'{attr.name_th}' ต้องเป็นตัวเลขที่ไม่ติดลบ")
            vtext = None
        elif attr.data_type == "bool":
            if vnum in (0, 1, True, False):
                vnum = 1.0 if vnum else 0.0
            elif vtext in ("true", "false", "มี", "ไม่มี"):
                vnum = 1.0 if vtext in ("true", "มี") else 0.0
            else:
                raise ValueError(f"'{attr.name_th}' ต้องเป็น มี/ไม่มี (value_num 1 หรือ 0)")
            vtext = None
        elif attr.data_type == "enum":
            if vtext not in (options_of(attr) or []):
                raise ValueError(f"'{attr.name_th}' ต้องเลือกจากตัวเลือกที่กำหนด")
            vnum = None
        else:  # text
            if vtext is None:
                raise ValueError(f"'{attr.name_th}' ต้องเป็นข้อความ")
            if len(vtext) > 100:
                raise ValueError(f"'{attr.name_th}' ยาวเกิน 100 ตัวอักษร")
            vnum = None
        clean.append({"key": key, "value_num": vnum, "value_text": vtext})
    return clean


def replace_values(session: Session, product: models.Product, clean: List[dict], source: str = "seller") -> None:
    """แทนค่าสเปกทั้งชุด (ไม่ commit)"""
    clear_values_cache(session)
    for old in values_of(session, product.id).values():
        session.delete(old)
    session.flush()
    for v in clean:
        session.add(models.ProductAttributeValue(product_id=product.id, source=source, **v))


def drop_values_not_in_template(session: Session, product: models.Product) -> None:
    """เปลี่ยนหมวดแล้ว → ลบสเปกที่ไม่อยู่ในแม่แบบใหม่ (ไม่ commit)"""
    clear_values_cache(session)
    keys = {a.key for a in template(session, product.category_id)}
    for v in values_of(session, product.id).values():
        if v.key not in keys:
            session.delete(v)


def is_complete(session: Session, product: models.Product, values: Optional[dict] = None) -> bool:
    """กรอกสเปกที่จำเป็นของหมวดครบ → ได้ป้าย "ข้อมูลครบ" """
    tmpl = template(session, product.category_id)
    if not tmpl:
        return False
    values = values if values is not None else values_of(session, product.id)
    return all(a.key in values for a in tmpl if a.required)


def attribute_reads(
    session: Session, product: models.Product, values: Optional[dict] = None
) -> List[dict]:
    """ผู้เรียกที่ดึง values มาแล้วให้ส่งเข้ามาด้วย จะได้ไม่ query ซ้ำ"""
    vals = values if values is not None else values_of(session, product.id)
    out = []
    for a in template(session, product.category_id):
        v = vals.get(a.key)
        if v is None:
            continue
        out.append(dict(
            key=a.key, name_th=a.name_th, unit=a.unit, group_name=a.group_name, data_type=a.data_type,
            value_num=v.value_num, value_text=v.value_text,
            display=display(a, v.value_num, v.value_text), source=v.source,
        ))
    return out
