"""ค่าส่ง (เฟส 2): เรทของร้าน + เรทเฉพาะภาค + ระยะเวลาส่ง และการหาจังหวัดของผู้ซื้อ

ใช้ engine เดียวกันทั้งหน้าเทียบ ใบเสนอค่าส่งในตะกร้า และตอน checkout จริง
เพื่อให้ราคารวมที่ผู้ซื้อเห็นตรงกับที่ต้องจ่ายจริง (ราคาบนหน้าเว็บต้องเป็นแหล่งความจริงเดียว)
ร้านที่ยังไม่ตั้งค่าส่ง = ค่าเริ่มต้น 40 บาท ส่งฟรีเมื่อซื้อครบ 500 (เหมือนระบบเดิม)
"""
from typing import Iterable, List, Optional, Tuple

from sqlmodel import Session, select

from app import models

DEFAULT_FLAT_RATE = 40
DEFAULT_FREE_OVER = 500
DEFAULT_DAYS = (2, 4)

BKK = "กรุงเทพและปริมณฑล"
CENTRAL = "ภาคกลาง"
NORTH = "ภาคเหนือ"
NORTHEAST = "ภาคตะวันออกเฉียงเหนือ"
EAST = "ภาคตะวันออก"
WEST = "ภาคตะวันตก"
SOUTH = "ภาคใต้"
REGIONS = [BKK, CENTRAL, NORTH, NORTHEAST, EAST, WEST, SOUTH]

_BY_REGION = {
    BKK: ["กรุงเทพมหานคร", "นนทบุรี", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร", "นครปฐม"],
    CENTRAL: [
        "พระนครศรีอยุธยา", "อ่างทอง", "ลพบุรี", "สิงห์บุรี", "ชัยนาท", "สระบุรี",
        "นครนายก", "สุพรรณบุรี", "สมุทรสงคราม", "นครสวรรค์", "อุทัยธานี",
        "กำแพงเพชร", "พิจิตร", "พิษณุโลก", "สุโขทัย", "เพชรบูรณ์",
    ],
    NORTH: [
        "เชียงใหม่", "เชียงราย", "ลำปาง", "ลำพูน", "แม่ฮ่องสอน", "น่าน", "พะเยา",
        "แพร่", "อุตรดิตถ์",
    ],
    NORTHEAST: [
        "นครราชสีมา", "บุรีรัมย์", "สุรินทร์", "ศรีสะเกษ", "อุบลราชธานี", "ยโสธร",
        "ชัยภูมิ", "อำนาจเจริญ", "บึงกาฬ", "หนองบัวลำภู", "ขอนแก่น", "อุดรธานี",
        "เลย", "หนองคาย", "มหาสารคาม", "ร้อยเอ็ด", "กาฬสินธุ์", "สกลนคร",
        "นครพนม", "มุกดาหาร",
    ],
    EAST: ["ชลบุรี", "ระยอง", "จันทบุรี", "ตราด", "ฉะเชิงเทรา", "ปราจีนบุรี", "สระแก้ว"],
    WEST: ["ตาก", "ราชบุรี", "กาญจนบุรี", "เพชรบุรี", "ประจวบคีรีขันธ์"],
    SOUTH: [
        "ชุมพร", "ระนอง", "สุราษฎร์ธานี", "พังงา", "ภูเก็ต", "กระบี่",
        "นครศรีธรรมราช", "ตรัง", "พัทลุง", "สตูล", "สงขลา", "ปัตตานี", "ยะลา", "นราธิวาส",
    ],
}

PROVINCES: List[Tuple[str, str]] = [(p, r) for r in REGIONS for p in _BY_REGION[r]]
PROVINCE_REGION = dict(PROVINCES)
assert len(PROVINCE_REGION) == 77

# ชื่อเรียกสั้น/สะกดอื่นที่เจอบ่อยในที่อยู่
_ALIASES = {"กรุงเทพ": "กรุงเทพมหานคร", "กทม": "กรุงเทพมหานคร", "อยุธยา": "พระนครศรีอยุธยา",
            "โคราช": "นครราชสีมา"}


def region_of(province: Optional[str]) -> Optional[str]:
    return PROVINCE_REGION.get(province) if province else None


def normalize_province(raw: Optional[str]) -> Optional[str]:
    """คืนชื่อจังหวัดมาตรฐาน หรือ None ถ้าไม่ใช่ 1 ใน 77 จังหวัด"""
    if not raw:
        return None
    name = raw.strip().removeprefix("จังหวัด").removeprefix("จ.").strip()
    if name in PROVINCE_REGION:
        return name
    return _ALIASES.get(name)


def detect_province(address: Optional[str]) -> Optional[str]:
    """หาชื่อจังหวัดในที่อยู่แบบข้อความอิสระ — เลือกตัวที่อยู่ท้ายสุด (จังหวัดมักอยู่ท้ายที่อยู่)"""
    if not address:
        return None
    best, best_pos = None, -1
    names = list(PROVINCE_REGION) + list(_ALIASES)
    for name in names:
        pos = address.rfind(name)
        # ชื่อยาวกว่าชนะเมื่อตำแหน่งทับกัน (เช่น "กรุงเทพมหานคร" vs "กรุงเทพ")
        if pos > best_pos or (pos == best_pos and pos >= 0 and len(name) > len(best or "")):
            best, best_pos = name, pos
    return normalize_province(best) if best_pos >= 0 else None


# ---------------------------------------------------------------- เรทของร้าน

def get_shop_shipping(session: Session, shop_id: Optional[int]) -> models.ShopShipping:
    """ค่าส่งของร้าน (ร้านที่ยังไม่ตั้ง → object ค่าเริ่มต้น ไม่บันทึกลง DB)"""
    cfg = session.get(models.ShopShipping, shop_id) if shop_id else None
    if cfg is None:
        cfg = models.ShopShipping(
            shop_id=shop_id or 0, flat_rate=DEFAULT_FLAT_RATE, free_over=DEFAULT_FREE_OVER,
            days_min=DEFAULT_DAYS[0], days_max=DEFAULT_DAYS[1],
        )
    return cfg


def get_region_rates(session: Session, shop_id: Optional[int]) -> List[models.ShopShippingRegion]:
    if not shop_id:
        return []
    return list(session.exec(
        select(models.ShopShippingRegion).where(models.ShopShippingRegion.shop_id == shop_id)
    ).all())


def rate_for(session: Session, shop_id: Optional[int], province: Optional[str]) -> Tuple[int, int, int]:
    """(ค่าส่ง, วันเร็วสุด, วันช้าสุด) ก่อนพิจารณาส่งฟรี"""
    cfg = get_shop_shipping(session, shop_id)
    region = region_of(province)
    if region:
        for r in get_region_rates(session, shop_id):
            if r.region == region:
                return r.rate, r.days_min, r.days_max
    return cfg.flat_rate, cfg.days_min, cfg.days_max


def quote(
    session: Session,
    shop_id: Optional[int],
    products_qty: Iterable[Tuple[models.Product, int]],
    province: Optional[str],
) -> dict:
    """ค่าส่งของ 1 ออเดอร์ (1 ร้าน): ฟรีถ้าทุกชิ้นส่งฟรี หรือยอดถึง free_over; ไม่งั้นเรทภาค/เรทร้าน"""
    entries = list(products_qty)
    subtotal = sum(p.price * q for p, q in entries)
    cfg = get_shop_shipping(session, shop_id)
    fee, dmin, dmax = rate_for(session, shop_id, province)
    all_free = bool(entries) and all(p.free_shipping for p, _ in entries)
    free_reason = None
    if all_free:
        free_reason = "item"           # สินค้านี้ส่งฟรี
    elif cfg.free_over is not None and subtotal >= cfg.free_over:
        free_reason = "threshold"      # ร้านส่งฟรีเมื่อซื้อครบ free_over
    if free_reason:
        fee = 0
    return {"subtotal": subtotal, "fee": fee, "days_min": dmin, "days_max": dmax,
            "free_reason": free_reason, "free_over": cfg.free_over}


# ---------------------------------------------------------------- จังหวัดผู้ซื้อ

def resolve_user_province(session: Session, user: Optional[models.User]) -> Tuple[Optional[str], Optional[str]]:
    """(จังหวัด, ที่มา) — ที่อยู่บัญชีก่อน แล้วจึงออเดอร์ล่าสุด (ช่อง province หรือเดาจากข้อความที่อยู่)"""
    if user is None:
        return None, None
    if normalize_province(user.province):
        return normalize_province(user.province), "account"
    last = session.exec(
        select(models.Order).where(models.Order.buyer_id == user.id).order_by(models.Order.id.desc())
    ).first()
    if last is not None:
        prov = normalize_province(last.province) or detect_province(last.address)
        if prov:
            return prov, "order"
    return None, None
