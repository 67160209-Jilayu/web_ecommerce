"""สรุปยอดขายสำหรับหน้าแดชบอร์ดร้านค้า

ตั้งใจให้ "ดูแล้วเข้าใจทันที" ไม่ใช่รายงานบัญชี จึงเลือกเฉพาะตัวเลขที่เจ้าของร้าน
ใช้ตัดสินใจได้จริง: ขายได้เท่าไหร่ ต้องรีบทำอะไร อะไรขายดี อะไรใกล้หมด

หลักการนับ:
- "ยอดขาย" นับเฉพาะออเดอร์ที่ชำระเงินแล้ว (PAID ขึ้นไป) และไม่นับที่ยกเลิก
  เพราะออเดอร์ที่ยังรอชำระอาจไม่เกิดขึ้นจริง
- ใช้ `subtotal` ไม่ใช่ `total` เพราะค่าส่งไม่ใช่รายได้ของร้าน
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List

from sqlmodel import Session, select

from app import models, schemas
from app.models import OrderStatus

# สถานะที่ถือว่า "ขายได้แล้ว" — ชำระเงินแล้วและยังไม่ถูกยกเลิก
EARNED_STATUSES = (
    OrderStatus.PAID,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
    OrderStatus.COMPLETED,
)

# สถานะที่ร้านต้องลงมือทำอะไรบางอย่าง
ACTION_STATUSES = {
    OrderStatus.PENDING_PAYMENT: "รอลูกค้าชำระเงิน",
    OrderStatus.PAID: "รอคุณจัดส่ง",
    OrderStatus.SHIPPED: "รอลูกค้ากดรับของ",
}

LOW_STOCK_THRESHOLD = 5
TREND_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    """แถวเก่าบางแถวไม่มี timezone ติดมา — เทียบเวลาตรงๆ จะ error"""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def build(session: Session, shop: models.Shop) -> schemas.SellerDashboard:
    orders = session.exec(
        select(models.Order).where(models.Order.shop_id == shop.id)
    ).all()

    now = _now()
    start_30 = now - timedelta(days=30)
    start_60 = now - timedelta(days=60)
    start_trend = (now - timedelta(days=TREND_DAYS - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    earned = [o for o in orders if o.status in EARNED_STATUSES]

    revenue_all = sum(o.subtotal for o in earned)
    revenue_30 = sum(o.subtotal for o in earned if _as_utc(o.created_at) >= start_30)
    revenue_prev_30 = sum(
        o.subtotal
        for o in earned
        if start_60 <= _as_utc(o.created_at) < start_30
    )

    # เปลี่ยนแปลงกี่ % เทียบกับ 30 วันก่อนหน้า (ไม่มีฐานเดิม = ไม่คำนวณ)
    change_pct = None
    if revenue_prev_30 > 0:
        change_pct = round((revenue_30 - revenue_prev_30) / revenue_prev_30 * 100, 1)

    # ---------- สิ่งที่ต้องทำ ----------
    todo: List[schemas.DashboardTodo] = []
    for status, label in ACTION_STATUSES.items():
        count = sum(1 for o in orders if o.status == status)
        if count:
            todo.append(schemas.DashboardTodo(status=status, label=label, count=count))

    # ---------- ยอดขายรายวัน 7 วันล่าสุด ----------
    per_day = defaultdict(lambda: {"revenue": 0, "orders": 0})
    for o in earned:
        created = _as_utc(o.created_at)
        if created >= start_trend:
            key = created.date().isoformat()
            per_day[key]["revenue"] += o.subtotal
            per_day[key]["orders"] += 1

    trend = []
    for i in range(TREND_DAYS):
        day = (start_trend + timedelta(days=i)).date().isoformat()
        trend.append(
            schemas.DashboardDay(
                date=day,
                revenue=per_day[day]["revenue"],
                orders=per_day[day]["orders"],
            )
        )

    # ---------- สินค้าขายดี ----------
    sold = defaultdict(lambda: {"name": "", "qty": 0, "revenue": 0, "image": "📦", "cover": None})
    earned_ids = {o.id for o in earned}
    if earned_ids:
        items = session.exec(
            select(models.OrderItem).where(models.OrderItem.order_id.in_(earned_ids))
        ).all()
        for it in items:
            row = sold[it.product_id]
            row["name"] = it.product_name
            row["qty"] += it.quantity
            row["revenue"] += it.subtotal
            row["image"] = it.product_image
            row["cover"] = it.product_cover_url

    top_products = [
        schemas.DashboardProduct(
            product_id=pid,
            name=row["name"],
            image=row["image"],
            cover_url=row["cover"],
            quantity=row["qty"],
            revenue=row["revenue"],
        )
        for pid, row in sorted(sold.items(), key=lambda kv: -kv[1]["qty"])[:5]
    ]

    # ---------- สินค้าใกล้หมด ----------
    products = session.exec(
        select(models.Product).where(
            models.Product.shop_id == shop.id,
            models.Product.is_active == True,  # noqa: E712
        )
    ).all()
    low_stock = [
        schemas.DashboardStock(
            product_id=p.id, name=p.name, image=p.image, cover_url=p.cover_url, stock=p.stock
        )
        for p in sorted(products, key=lambda p: p.stock)
        if p.stock <= LOW_STOCK_THRESHOLD
    ][:5]

    order_count = len(earned)
    return schemas.SellerDashboard(
        revenue_total=revenue_all,
        revenue_30d=revenue_30,
        revenue_change_pct=change_pct,
        order_count=order_count,
        avg_order_value=round(revenue_all / order_count) if order_count else 0,
        cancelled_count=sum(1 for o in orders if o.status == OrderStatus.CANCELLED),
        rating=round(shop.rating, 2),
        review_count=shop.review_count,
        active_product_count=len(products),
        todo=todo,
        trend=trend,
        top_products=top_products,
        low_stock=low_stock,
    )
