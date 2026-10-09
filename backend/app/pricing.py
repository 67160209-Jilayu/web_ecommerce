"""ระบบราคาเบื้องหลัง (เฟส 1): ประวัติราคา, ราคาก่อนลดที่ระบบคำนวณ, ตรวจขึ้นราคาก่อนลด, notice ตะกร้า

หลักการ
- ผู้ซื้อไม่เห็นประวัติราคา เห็นแค่ "ราคาก่อนลด" (ราคาขีดฆ่า) ที่ระบบคำนวณ + % ส่วนลด
- ราคาก่อนลด = ราคาต่ำสุดใน 30 วันก่อนราคาปัจจุบันเริ่มใช้ (แนวเดียวกับ EU Omnibus Art. 6a)
  ผู้ขายพิมพ์ราคาขีดฆ่าเองไม่ได้แล้ว
- ถ้าขึ้นราคา ≥ 15% ภายใน 14 วันก่อนเริ่มลด → ซ่อน % ส่วนลด (ยังแสดงราคาขีดฆ่าได้ เพราะเป็นราคาจริง)
  ระหว่างช่วงผ่อนผันแค่เตือนใน dashboard ผู้ขาย
- ไม่มี SKU/variant ในระบบนี้ จึงใช้ sku_id = product.id

ลำดับการเรียก (ไม่มี queue ภายนอก)
1. ก่อน commit ที่แก้ราคา/สต็อก: `record_price_state(session, product, source)` (transaction เดียวกัน)
2. หลัง commit: `after_price_change(session, product_ids)` → คำนวณ sku_price_ref ใหม่ + ซิงก์ notice ตะกร้า
3. งานกลางคืน: `nightly_recompute(session)` หรือ `python -m app.pricing` (เรียกจาก cron/Task Scheduler)

เวลาทั้งหมดในตารางใหม่เป็น UTC แบบ naive เพราะ SQLite คืนค่า naive เสมอ
ทุกฟังก์ชันที่ขึ้นกับเวลารับ `now=` ได้ (ใช้ในเทสต์)
"""
import math
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import object_session
from sqlmodel import Session, select

from app import config, models
from app.models import PriceSource, PriceType


# =====================================================================
# เวลา
# =====================================================================

def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def naive(dt: Optional[datetime]) -> Optional[datetime]:
    """แปลงเป็น UTC naive เพื่อเทียบกันได้ทั้งค่าจาก PostgreSQL/SQLite/โค้ด"""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _now(now: Optional[datetime]) -> datetime:
    return naive(now) if now is not None else utcnow_naive()


def grace_end_date() -> date:
    return config.PRICE_GRACE_START + timedelta(days=config.PRICE_GRACE_DAYS)


def grace_active(now: Optional[datetime] = None) -> bool:
    """อยู่ในช่วงผ่อนผันไหม (ระหว่างนี้ยังไม่ซ่อน % ส่วนลดบนหน้าเว็บ)"""
    if not config.PRICE_GRACE_ENABLED:
        return False
    return _now(now).date() < grace_end_date()


# =====================================================================
# ประวัติราคา
# =====================================================================

def _history(session: Session, sku_id: int) -> List[models.SkuPriceHistory]:
    return list(
        session.exec(
            select(models.SkuPriceHistory)
            .where(models.SkuPriceHistory.sku_id == sku_id)
            .order_by(models.SkuPriceHistory.valid_from, models.SkuPriceHistory.id)
        ).all()
    )


def _open_row(session: Session, sku_id: int) -> Optional[models.SkuPriceHistory]:
    return session.exec(
        select(models.SkuPriceHistory)
        .where(
            models.SkuPriceHistory.sku_id == sku_id,
            models.SkuPriceHistory.valid_to == None,  # noqa: E711
        )
        .order_by(models.SkuPriceHistory.valid_from.desc(), models.SkuPriceHistory.id.desc())
    ).first()


def _min_price_between(
    rows: Iterable[models.SkuPriceHistory], start: datetime, end: datetime
) -> Optional[int]:
    """ราคาต่ำสุดของช่วงราคาที่มีผลอยู่ในช่วง [start, end)

    กันส่วนลดหลอก: ราคาหนึ่งๆ จะนับเป็นราคาอ้างอิงได้ก็ต่อเมื่อใช้จริงรวมกัน
    ≥ PRICE_REF_MIN_DAYS วันภายในหน้าต่างนี้ (เช่น ตั้ง 999 ไว้ 1 นาทีแล้วลดเหลือ 499 → ไม่นับ 999)
    """
    min_seconds = config.PRICE_REF_MIN_DAYS * 86400
    durations: dict = {}
    for r in rows:
        vf = max(naive(r.valid_from), start)
        vt = min(naive(r.valid_to) if r.valid_to is not None else end, end)
        if vt > vf:
            durations[r.effective_price] = (
                durations.get(r.effective_price, 0.0) + (vt - vf).total_seconds()
            )
    if not durations:
        return None
    # ต้องมีอย่างน้อย 1 ราคาที่ใช้จริงรวม ≥ เกณฑ์วัน ถึงจะมีราคาอ้างอิง (กันตั้งราคาสูงแป๊บเดียวแล้วลด)
    # และเมื่อมีแล้ว ใช้ราคาต่ำสุดของ "ทุกราคา" ในหน้าต่าง รวมราคาต่ำที่ใช้สั้นๆ (เช่น flash sale 1 วัน)
    # เพราะราคาต่ำที่ผู้ซื้อเคยจ่ายจริงต้องไม่ถูกข้ามไป
    if not any(secs >= min_seconds for secs in durations.values()):
        return None
    return min(durations)


def max_increase(
    rows: Iterable[models.SkuPriceHistory], start: datetime, end: datetime, include_end: bool
) -> Tuple[Optional[float], Optional[datetime]]:
    """% ขึ้นราคาสูงสุดแบบสะสมของช่วงราคาที่มีผลใน [start, end) (หรือ [start, end] ถ้า include_end)

    นับแบบสะสมจากราคาต่ำสุดก่อนหน้า: 100 → 110 → 120 = ขึ้น 20% (ไม่ใช่ 10% สองครั้ง)
    กันการทยอยขึ้นทีละนิดเพื่อหลบกฎ
    คืน (percent, เวลาที่ราคาสูงสุดนั้นเริ่มใช้) หรือ (None, None) ถ้าไม่มีช่วงราคาในหน้าต่างนี้
    """
    levels = []
    for r in rows:
        vf, vt = naive(r.valid_from), naive(r.valid_to)
        starts_ok = vf <= end if include_end else vf < end
        if starts_ok and (vt is None or vt > start):
            levels.append((r.effective_price, vf))
    if not levels:
        return None, None
    best, best_at = 0.0, None
    running_min = levels[0][0]
    for price, at in levels[1:]:
        if running_min > 0 and price > running_min:
            pct = (price - running_min) * 100.0 / running_min
            if pct > best:
                best, best_at = pct, at
        running_min = min(running_min, price)
    return round(best, 2), best_at


def _current_price_since(rows: List[models.SkuPriceHistory]) -> Optional[datetime]:
    """เวลาที่ราคาปัจจุบันเริ่มใช้ — ย้อนข้ามแถวที่ราคาเท่าเดิม (เปลี่ยนแค่สต็อก) ไปหาจุดเริ่มจริง"""
    if not rows:
        return None
    price = rows[-1].effective_price
    i = len(rows) - 1
    while i > 0 and rows[i - 1].effective_price == price:
        i -= 1
    return naive(rows[i].valid_from)


def record_price_state(
    session: Session,
    product: models.Product,
    source: str = PriceSource.SELLER,
    now: Optional[datetime] = None,
) -> Optional[models.SkuPriceHistory]:
    """จดประวัติถ้าราคา/สถานะมีสต็อกเปลี่ยนจริง — เรียกก่อน commit (transaction เดียวกับการแก้ราคา)

    คืนแถวใหม่ หรือ None ถ้าไม่มีอะไรเปลี่ยน (ไม่ต้องเรียก after_price_change)
    """
    if product.id is None:
        session.flush()
    now = _now(now)
    in_stock = (product.stock or 0) > 0
    price = product.price

    current = _open_row(session, product.id)
    if (
        current is not None
        and current.list_price == price
        and current.effective_price == price
        and current.in_stock == in_stock
    ):
        return None

    if current is not None and current.effective_price == price:
        price_type = current.price_type  # เปลี่ยนแค่สต็อก ราคาเดิม → ประเภทเดิม
    else:
        rows = _history(session, product.id)
        ref = _min_price_between(rows, now - timedelta(days=config.PRICE_REF_WINDOW_DAYS), now)
        price_type = PriceType.DISCOUNT if ref is not None and ref > price else PriceType.REGULAR

    if current is not None:
        # นาฬิกาบางระบบ (เช่น Windows) ละเอียดแค่ ~15ms — สองการแก้ติดกันอาจได้เวลาเท่ากัน
        # บังคับให้ valid_from ของแถวใหม่มากกว่าแถวเดิมเสมอ ไม่งั้นลำดับช่วงราคาจะเพี้ยน
        prev_from = naive(current.valid_from)
        if now <= prev_from:
            now = prev_from + timedelta(microseconds=1)
        current.valid_to = now
        session.add(current)

    row = models.SkuPriceHistory(
        sku_id=product.id,
        shop_id=product.shop_id,
        list_price=price,
        effective_price=price,
        price_type=price_type,
        in_stock=in_stock,
        source=source,
        valid_from=now,
    )
    session.add(row)
    return row


# =====================================================================
# sku_price_ref (ราคาก่อนลด + ตรวจขึ้นราคาก่อนลด)
# =====================================================================

def recompute_price_ref(
    session: Session, sku_id: int, now: Optional[datetime] = None
) -> Optional[models.SkuPriceRef]:
    """คำนวณ sku_price_ref ของ SKU เดียวจากประวัติ (ไม่ commit — ผู้เรียก commit เอง)"""
    rows = _history(session, sku_id)
    ref = session.get(models.SkuPriceRef, sku_id)
    if not rows:
        if ref is not None:
            session.delete(ref)
        return None

    since = _current_price_since(rows)
    prior = [r for r in rows if naive(r.valid_from) < since]
    min_30d = _min_price_between(
        prior, since - timedelta(days=config.PRICE_REF_WINDOW_DAYS), since
    )
    max_inc, _ = max_increase(
        prior, since - timedelta(days=config.PRICE_RAISE_WINDOW_DAYS), since, include_end=False
    )

    if ref is None:
        ref = models.SkuPriceRef(sku_id=sku_id)
    ref.min_30d = min_30d
    ref.max_increase_14d = max_inc
    ref.effective_price = rows[-1].effective_price
    ref.price_since = since
    ref.updated_at = _now(now)
    session.add(ref)
    return ref


def history(session: Session, sku_id: int) -> List[models.SkuPriceHistory]:
    """ประวัติทั้งหมดของ SKU (เก่า → ใหม่) — ใช้ภายใน/dashboard ผู้ขายเท่านั้น"""
    return _history(session, sku_id)


def get_price_ref(product: models.Product) -> Optional[models.SkuPriceRef]:
    s = object_session(product)
    return s.get(models.SkuPriceRef, product.id) if s is not None and product.id else None


class PriceDisplay:
    """ผลคำนวณราคาที่จะแสดง (ใช้ทั้งหน้าเว็บผู้ซื้อและ dashboard ผู้ขาย)"""

    def __init__(self):
        self.ref_price: Optional[int] = None          # ราคาขีดฆ่าที่ผู้ซื้อเห็น
        self.discount_percent: Optional[int] = None   # % ที่คำนวณได้ (แม้จะถูกซ่อน)
        self.raise_flagged: bool = False              # ขึ้นราคา ≥ เกณฑ์ ก่อนเริ่มลด
        self.discount_hidden: bool = False            # ผู้ซื้อไม่เห็น % (บังคับใช้กฎแล้ว)

    @property
    def shown_percent(self) -> Optional[int]:
        return None if self.discount_hidden else self.discount_percent


def compute_display(
    product: models.Product,
    ref: Optional[models.SkuPriceRef] = None,
    now: Optional[datetime] = None,
) -> PriceDisplay:
    d = PriceDisplay()
    if ref is None:
        ref = get_price_ref(product)
    # ref ไม่ตรงกับราคาปัจจุบัน = ยังไม่อัปเดต → ไม่แสดงส่วนลด (ปลอดภัยไว้ก่อน)
    if ref is None or ref.effective_price != product.price or ref.min_30d is None:
        return d
    if ref.min_30d <= product.price:
        return d

    d.ref_price = ref.min_30d
    pct = math.floor((ref.min_30d - product.price) * 100 / ref.min_30d)
    d.discount_percent = pct if pct >= 1 else None
    d.raise_flagged = (
        ref.max_increase_14d is not None and ref.max_increase_14d >= config.PRICE_RAISE_PERCENT
    )
    d.discount_hidden = d.raise_flagged and not grace_active(now)
    return d


# =====================================================================
# Notice ราคาลดในตะกร้า
# =====================================================================

def notice_qualifies(old_price: Optional[int], new_price: int) -> bool:
    """ลดลง ≥ CART_NOTICE_MIN_PERCENT % หรือ ≥ CART_NOTICE_MIN_BAHT บาท (อย่างใดอย่างหนึ่ง)"""
    if old_price is None or old_price <= 0:
        return False
    drop = old_price - new_price
    if drop <= 0:
        return False
    return drop >= config.CART_NOTICE_MIN_BAHT or drop * 100 >= config.CART_NOTICE_MIN_PERCENT * old_price


def _notice_for_item(session: Session, cart_item_id: int) -> Optional[models.CartPriceNotice]:
    return session.exec(
        select(models.CartPriceNotice).where(models.CartPriceNotice.cart_item_id == cart_item_id)
    ).first()


def delete_notice_for_item(session: Session, cart_item_id: Optional[int]) -> None:
    """ต้องเรียกก่อนลบ cart_item เสมอ (FK) — สินค้าออกจากตะกร้า = notice หาย"""
    if cart_item_id is None:
        return
    notice = _notice_for_item(session, cart_item_id)
    if notice is not None:
        session.delete(notice)
        session.flush()


def sync_item_notice(
    session: Session,
    item: models.CartItem,
    user_id: Optional[int],
    now: Optional[datetime] = None,
) -> Optional[models.CartPriceNotice]:
    """สร้าง/อัปเดต/ลบ notice ของ cart_item เดียวให้ตรงกับราคาปัจจุบัน (ไม่ commit)

    - ตะกร้า guest (user_id None) / สินค้าปิดขาย / ไม่ถึงเกณฑ์ → ลบ notice
    - ลดเพิ่ม → อัปเดตแถวเดิม และตั้ง read_at = None ให้แสดงอีกครั้ง
    - ราคาขึ้นแต่ยังถึงเกณฑ์ → อัปเดตราคา คงสถานะอ่านแล้วไว้
    """
    product = item.product
    notice = _notice_for_item(session, item.id)
    ok = (
        user_id is not None
        and product is not None
        and product.is_active
        and notice_qualifies(item.price_at_add, product.price)
    )
    if not ok:
        if notice is not None:
            session.delete(notice)
        return None

    if notice is None:
        notice = models.CartPriceNotice(
            user_id=user_id,
            sku_id=item.product_id,
            cart_item_id=item.id,
            old_price=item.price_at_add,
            new_price=product.price,
            created_at=_now(now),
        )
    else:
        if product.price < notice.new_price:
            notice.read_at = None
            notice.created_at = _now(now)
        notice.user_id = user_id
        notice.old_price = item.price_at_add
        notice.new_price = product.price
    session.add(notice)
    return notice


def sync_cart_notices(
    session: Session,
    product_id: Optional[int] = None,
    cart_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> int:
    """ซิงก์ notice ของ cart_item ทั้งหมด (หรือเฉพาะสินค้า/ตะกร้า) — ไม่ commit; คืนจำนวนที่มี notice"""
    stmt = select(models.CartItem, models.Cart).where(models.CartItem.cart_id == models.Cart.id)
    if product_id is not None:
        stmt = stmt.where(models.CartItem.product_id == product_id)
    if cart_id is not None:
        stmt = stmt.where(models.Cart.id == cart_id)
    count = 0
    for item, cart in session.exec(stmt).all():
        if sync_item_notice(session, item, cart.user_id, now=now) is not None:
            count += 1
    return count


# =====================================================================
# จุดเรียกจาก crud / งานกลางคืน
# =====================================================================

def after_price_change(
    session: Session, product_ids: Iterable[int], now: Optional[datetime] = None
) -> None:
    """เรียกหลัง commit ที่ราคา/สต็อกเปลี่ยน: คำนวณ ref ใหม่ + ซิงก์ notice ตะกร้า แล้ว commit

    ถ้าพังจะไม่ทำให้ request หลักล้ม (ข้อมูลหลักถูก commit ไปแล้ว) งานกลางคืนจะแก้ให้ตรงอีกรอบ
    """
    try:
        for pid in {p for p in product_ids if p is not None}:
            recompute_price_ref(session, pid, now=now)
            sync_cart_notices(session, product_id=pid, now=now)
        session.commit()
    except Exception as err:  # noqa: BLE001
        session.rollback()
        print(f"[pricing] after_price_change ล้มเหลว (งานกลางคืนจะคำนวณใหม่): {err!r}", flush=True)


def backfill_missing_history(session: Session, now: Optional[datetime] = None) -> int:
    """สินค้าที่ยังไม่มีประวัติเลย (เช่น มีอยู่ก่อนเปิดระบบนี้) → เปิดแถวแรกด้วยราคาปัจจุบัน (ไม่ commit)"""
    has_history = set(session.exec(select(models.SkuPriceHistory.sku_id).distinct()).all())
    added = 0
    for product in session.exec(select(models.Product)).all():
        if product.id not in has_history:
            record_price_state(session, product, PriceSource.SYSTEM, now=now)
            added += 1
    return added


def backfill_cart_price_at_add(session: Session) -> int:
    """cart_item เก่าที่ยังไม่มี price_at_add → ใช้ราคาปัจจุบัน (notice จะเริ่มนับจากนี้ไป) (ไม่ commit)"""
    items = session.exec(
        select(models.CartItem).where(models.CartItem.price_at_add == None)  # noqa: E711
    ).all()
    for item in items:
        if item.product is not None:
            item.price_at_add = item.product.price
            session.add(item)
    return len(items)


def nightly_recompute(session: Session, now: Optional[datetime] = None) -> dict:
    """งานกลางคืน (02:00): เติมประวัติที่ขาด → คำนวณ sku_price_ref ทุก SKU → ซิงก์ notice ทุกตะกร้า"""
    backfilled = backfill_missing_history(session, now=now)
    session.flush()
    sku_ids = list(session.exec(select(models.SkuPriceHistory.sku_id).distinct()).all())
    for sku_id in sku_ids:
        recompute_price_ref(session, sku_id, now=now)
    notices = sync_cart_notices(session, now=now)
    session.commit()
    return {"backfilled": backfilled, "refs": len(sku_ids), "notices": notices}


if __name__ == "__main__":  # python -m app.pricing  (รันจากโฟลเดอร์ backend)
    from app.database import create_db_and_tables, engine

    create_db_and_tables()
    with Session(engine) as s:
        print(nightly_recompute(s))
