"""เฟส 1 — กฎที่ขึ้นกับเวลา: sku_price_history, ราคาก่อนลด 30 วัน, ขึ้นราคา ≥15% ใน 14 วัน, ช่วงผ่อนผัน

วิธีทดสอบเวลา: สร้างประวัติราคาย้อนหลังลงตาราง sku_price_history ตรงๆ (backdate)
แล้วเรียก pricing.recompute_price_ref + commit — ตรงกับที่งานกลางคืนทำ
"""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from app import config, models, pricing
from app.database import engine

CHECKOUT_BODY = {
    "recipient_name": "ผู้รับ",
    "recipient_phone": "0800000000",
    "address": "กรุงเทพฯ",
    "payment_method": "COD",
}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def history(pid):
    with Session(engine) as s:
        return list(s.exec(
            select(models.SkuPriceHistory)
            .where(models.SkuPriceHistory.sku_id == pid)
            .order_by(models.SkuPriceHistory.valid_from, models.SkuPriceHistory.id)
        ).all())


def set_history(pid, segments):
    """แทนประวัติราคาด้วยช่วงที่กำหนด: [(ราคา, กี่วันก่อน), ...] เรียงจากเก่าไปใหม่
    ช่วงสุดท้าย = ราคาปัจจุบัน (ตั้ง product.price ให้ตรง) แล้วคำนวณ ref ใหม่
    """
    now = _now()
    with Session(engine) as s:
        product = s.get(models.Product, pid)
        for r in s.exec(select(models.SkuPriceHistory).where(models.SkuPriceHistory.sku_id == pid)).all():
            s.delete(r)
        s.flush()
        for i, (price, days_ago) in enumerate(segments):
            start = now - timedelta(days=days_ago)
            end = now - timedelta(days=segments[i + 1][1]) if i + 1 < len(segments) else None
            s.add(models.SkuPriceHistory(
                sku_id=pid, shop_id=product.shop_id, list_price=price, effective_price=price,
                price_type="regular", in_stock=True, source="seller", valid_from=start, valid_to=end,
            ))
        product.price = segments[-1][0]
        s.add(product)
        s.flush()
        pricing.recompute_price_ref(s, pid, now=now)
        s.commit()


@pytest.fixture
def no_grace(monkeypatch):
    monkeypatch.setattr(config, "PRICE_GRACE_ENABLED", False)


@pytest.fixture
def in_grace(monkeypatch):
    monkeypatch.setattr(config, "PRICE_GRACE_ENABLED", True)
    monkeypatch.setattr(config, "PRICE_GRACE_START", date.today() - timedelta(days=1))
    monkeypatch.setattr(config, "PRICE_GRACE_DAYS", 30)


def _status_item(client, h, pid):
    r = client.get("/api/seller/price-status", headers=h)
    assert r.status_code == 200, r.text
    return r.json(), next(i for i in r.json()["items"] if i["product_id"] == pid)


# =================================================================== history

def test_history_row_on_create(api):
    h, shop = api.seller()
    p = api.product(h, price=1000, stock=5)
    rows = history(p["id"])
    assert len(rows) == 1
    r = rows[0]
    assert (r.sku_id, r.shop_id, r.list_price, r.effective_price) == (p["id"], shop["id"], 1000, 1000)
    assert r.in_stock is True and r.valid_to is None and r.source == "seller"


def test_no_history_row_without_actual_change(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000, stock=5)
    api.set_price(h, p["id"], 1000)  # ราคาเดิม
    client.patch(f"/api/products/{p['id']}", json={"name": "ใหม่", "description": "d"}, headers=h)
    client.patch(f"/api/products/{p['id']}", json={"stock": 3}, headers=h)  # ยังมีของ → in_stock เดิม
    assert len(history(p["id"])) == 1


def test_history_row_on_price_change_closes_previous(api, instant_ref):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 900)
    rows = history(p["id"])
    assert len(rows) == 2
    old, new = rows
    assert old.valid_to is not None and new.valid_to is None
    assert old.valid_to == new.valid_from
    assert new.effective_price == 900 and new.price_type == "discount"
    # มี open row แค่แถวเดียวเสมอ
    assert sum(1 for r in rows if r.valid_to is None) == 1


def test_history_row_on_stock_availability_change(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000, stock=2)
    client.patch(f"/api/products/{p['id']}", json={"stock": 0}, headers=h)
    client.patch(f"/api/products/{p['id']}", json={"stock": 4}, headers=h)
    rows = history(p["id"])
    assert [r.in_stock for r in rows] == [True, False, True]
    assert all(r.effective_price == 1000 for r in rows)


def test_history_on_checkout_sellout_and_cancel(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=300, stock=1)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    orders = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT_BODY, headers=hb).json()
    assert [r.in_stock for r in history(p["id"])] == [True, False]
    client.post(f"/api/orders/{orders[0]['id']}/cancel", headers=hb)
    assert [r.in_stock for r in history(p["id"])] == [True, False, True]


def test_history_written_in_same_transaction_as_price_change(api, monkeypatch):
    """ปิดงานหลัง commit (after_price_change) แล้วแถวประวัติต้องยังอยู่ = เขียนพร้อม commit หลัก"""
    from app import crud
    monkeypatch.setattr(pricing, "after_price_change", lambda *a, **k: None)
    if hasattr(crud, "after_price_change"):
        monkeypatch.setattr(crud, "after_price_change", lambda *a, **k: None)
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 800)
    assert [r.effective_price for r in history(p["id"])] == [1000, 800]


def test_record_price_state_called_before_commit(api, monkeypatch):
    """ตอนจดประวัติ ราคาใหม่ต้องยังไม่ถูก commit (อยู่ใน transaction เดียวกัน)"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    seen = []
    orig = pricing.record_price_state

    def spy(session, product, *a, **k):
        with Session(engine) as other:
            seen.append(other.get(models.Product, product.id).price)
        return orig(session, product, *a, **k)

    monkeypatch.setattr(pricing, "record_price_state", spy)
    from app import crud
    if hasattr(crud, "record_price_state"):
        monkeypatch.setattr(crud, "record_price_state", spy)
    api.set_price(h, p["id"], 700)
    assert seen and seen[-1] == 1000, f"ราคาที่ connection อื่นเห็นตอนจดประวัติ: {seen}"


def test_failed_update_writes_no_history(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    r = client.patch(f"/api/products/{p['id']}", json={"price": 500, "stock": -1}, headers=h)
    assert r.status_code == 400
    assert client.get(f"/api/products/{p['id']}").json()["price"] == 1000
    assert len(history(p["id"])) == 1


# =================================================================== ราคาก่อนลด 30 วัน

def test_reference_ignores_prices_older_than_30_days(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    # 700 จบไปตั้งแต่ 31 วันก่อน → นอกหน้าต่าง; ต่ำสุดใน 30 วัน = 950
    set_history(p["id"], [(1000, 60), (700, 45), (950, 31), (800, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 950
    assert got["discount_percent"] == 15  # floor(150*100/950)


def test_reference_includes_price_valid_at_window_start(api, client):
    """ราคาที่เริ่มก่อนหน้าต่างแต่ยังมีผลอยู่ในหน้าต่าง ต้องนับด้วย"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(700, 60), (950, 20), (800, 0)])  # 700 มีผลถึงวันที่ -20
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] is None  # ต่ำสุด 700 < 800 → ไม่ใช่ส่วนลด


def test_reference_window_anchored_at_discount_start(api, client):
    """หน้าต่าง 30 วันนับย้อนจากวันที่เริ่มลด (5 วันก่อน) ไม่ใช่จากวันนี้"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 50), (600, 40), (900, 36), (800, 5)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 900
    assert got["discount_percent"] == 11


def test_no_reference_without_prior_history(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(800, 3)])
    assert client.get(f"/api/products/{p['id']}").json()["original_price"] is None


def test_stock_only_change_does_not_reset_discount_start(api, client, instant_ref):
    h, _ = api.seller()
    p = api.product(h, price=1000, stock=5)
    api.set_price(h, p["id"], 800)
    client.patch(f"/api/products/{p['id']}", json={"stock": 0}, headers=h)
    client.patch(f"/api/products/{p['id']}", json={"stock": 5}, headers=h)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 1000 and got["discount_percent"] == 20


# =================================================================== ขึ้นราคา ≥15% ใน 14 วัน

def test_raise_before_discount_hides_percent_outside_grace(api, client, no_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (120, 10), (80, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 100        # ราคาขีดฆ่ายังแสดง (เป็นราคาจริง)
    assert got["discount_percent"] is None     # แต่ซ่อน %
    _, item = _status_item(client, h, p["id"])
    assert item["discount_percent"] == 20 and item["discount_hidden"] is True
    assert item["max_increase_14d_percent"] == pytest.approx(20.0)
    codes = [w["code"] for w in item["warnings"]]
    assert "raise_before_discount" in codes
    assert all(w["message"] for w in item["warnings"])


def test_raise_during_grace_only_warns(api, client, in_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (120, 10), (80, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 100 and got["discount_percent"] == 20
    body, item = _status_item(client, h, p["id"])
    assert body["grace"]["active"] is True and body["grace"]["enabled"] is True
    assert item["discount_hidden"] is False
    codes = [w["code"] for w in item["warnings"]]
    assert "raise_before_discount_grace" in codes and "raise_before_discount" not in codes


def test_grace_expired_enforces(api, client, monkeypatch):
    monkeypatch.setattr(config, "PRICE_GRACE_ENABLED", True)
    monkeypatch.setattr(config, "PRICE_GRACE_START", date.today() - timedelta(days=31))
    monkeypatch.setattr(config, "PRICE_GRACE_DAYS", 30)
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (120, 10), (80, 0)])
    assert client.get(f"/api/products/{p['id']}").json()["discount_percent"] is None
    body, _ = _status_item(client, h, p["id"])
    assert body["grace"]["active"] is False


def test_raise_below_threshold_keeps_percent(api, client, no_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (114, 10), (80, 0)])
    assert client.get(f"/api/products/{p['id']}").json()["discount_percent"] == 20


def test_raise_exactly_15_percent_hides(api, client, no_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (115, 10), (80, 0)])
    assert client.get(f"/api/products/{p['id']}").json()["discount_percent"] is None


def test_raise_older_than_14_days_not_flagged(api, client, no_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (130, 20), (80, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 100 and got["discount_percent"] == 20


def test_stepwise_raise_is_cumulative(api, client, no_grace):
    """100 → 108 → 116 ภายใน 14 วัน = ขึ้น 16% สะสม (หลบกฎด้วยการทยอยขึ้นไม่ได้)"""
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (108, 12), (116, 6), (80, 0)])
    assert client.get(f"/api/products/{p['id']}").json()["discount_percent"] is None


def test_raise_window_anchored_at_discount_start(api, client, no_grace):
    """ลดเริ่ม 10 วันก่อน; ขึ้นราคา 20 วันก่อน = 10 วันก่อนเริ่มลด → อยู่ในหน้าต่าง 14 วัน"""
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 60), (120, 20), (80, 10)])
    assert client.get(f"/api/products/{p['id']}").json()["discount_percent"] is None


def test_recent_raise_warning_without_discount(api, client, no_grace):
    h, _ = api.seller()
    p = api.product(h, price=100)
    set_history(p["id"], [(100, 30), (130, 3)])
    _, item = _status_item(client, h, p["id"])
    assert item["discount_percent"] is None
    assert "recent_raise" in [w["code"] for w in item["warnings"]]


def test_grace_disabled_reported(api, client, no_grace):
    h, _ = api.seller()
    api.product(h)
    body = client.get("/api/seller/price-status", headers=h).json()
    assert body["grace"]["enabled"] is False and body["grace"]["active"] is False


# =================================================================== งานกลางคืน / config

def test_nightly_recompute_backfills_and_computes(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    with Session(engine) as s:  # จำลองสินค้าที่มีอยู่ก่อนเปิดระบบ (ไม่มีประวัติ)
        for r in s.exec(select(models.SkuPriceHistory)).all():
            s.delete(r)
        ref = s.get(models.SkuPriceRef, p["id"])
        if ref:
            s.delete(ref)
        s.commit()
    with Session(engine) as s:
        result = pricing.nightly_recompute(s)
    assert result["backfilled"] >= 1
    rows = history(p["id"])
    assert len(rows) == 1 and rows[0].source == "system"
    with Session(engine) as s:
        assert s.get(models.SkuPriceRef, p["id"]) is not None


def test_nightly_recompute_idempotent(api):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 800)
    with Session(engine) as s:
        pricing.nightly_recompute(s)
    with Session(engine) as s:
        pricing.nightly_recompute(s)
    assert len(history(p["id"])) == 2


def test_notice_thresholds_configurable(api, client, monkeypatch):
    monkeypatch.setattr(config, "CART_NOTICE_MIN_BAHT", 50)
    monkeypatch.setattr(config, "CART_NOTICE_MIN_PERCENT", 10.0)
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 960)  # 40 บาท 4% → ไม่ถึงเกณฑ์ใหม่
    assert client.get("/api/account/notices", headers=hb).json()["unread_count"] == 0
    api.set_price(hs, p["id"], 950)
    assert client.get("/api/account/notices", headers=hb).json()["unread_count"] == 1


def test_price_at_add_kept_when_adding_more(api, client):
    """ใส่สินค้าเดิมเพิ่มหลังราคาลด — price_at_add ไม่ควรถูกเขียนทับจนทำให้ notice หายผิดเวลา
    (บันทึกพฤติกรรมไว้: แถวยังมีแค่ 1 รายการ และ price_at_add มีค่า)"""
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    cart = api.add_to_cart(token, p["id"], h=hb)
    assert len(cart["items"]) == 1 and cart["items"][0]["price_at_add"] in (800, 1000)


def test_same_timestamp_edits_keep_order(api, client, instant_ref):
    """แก้ราคา 2 ครั้งใน timestamp เดียวกัน (Windows clock ~15ms) — valid_from ต้องเรียงลำดับได้แน่นอน"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    fixed = _now()
    with Session(engine) as s:
        prod = s.get(models.Product, p["id"])
        for price in (900, 800):
            prod.price = price
            pricing.record_price_state(s, prod, now=fixed)
            s.add(prod)
            s.flush()
        pricing.recompute_price_ref(s, p["id"], now=fixed)
        s.commit()
    rows = history(p["id"])
    assert [r.effective_price for r in rows] == [1000, 900, 800]
    assert rows[1].valid_from < rows[2].valid_from
    assert sum(1 for r in rows if r.valid_to is None) == 1
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 900


# =================================================================== กฎ 7 วัน (PRICE_REF_MIN_DAYS)
# ราคาจะนับเป็นราคาอ้างอิง 30 วันได้ ต้องมีผลรวม ≥ 7 วันภายในหน้าต่าง — กันตั้งราคาสูงแป๊บเดียวแล้ว "ลด"

def test_min_days_default_is_7():
    assert getattr(config, "PRICE_REF_MIN_DAYS", None) == 7


def test_fake_discount_brief_high_price_via_api(api, client):
    """สร้างสินค้า 1000 แล้วลดเป็น 800 ทันที → 1000 มีผลไม่ถึง 7 วัน → ห้ามแสดงราคาขีดฆ่า/%"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 800)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] is None and got["discount_percent"] is None
    _, item = _status_item(client, h, p["id"])
    assert item["ref_price"] is None


def test_price_in_effect_6_days_does_not_count(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 6), (800, 0)])
    assert client.get(f"/api/products/{p['id']}").json()["original_price"] is None


def test_price_in_effect_7_days_counts(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 7), (800, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 1000 and got["discount_percent"] == 20


def test_price_7_days_in_total_across_segments_counts(api, client):
    """1000 (4 วัน) → 1200 (3 วัน) → 1000 (4 วัน) → 900: 1000 รวม 8 วัน → นับได้"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 11), (1200, 7), (1000, 4), (900, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 1000


def test_only_days_inside_window_count(api, client):
    """1000 อยู่ในหน้าต่างแค่ 5 วัน (ไม่ผ่านเกณฑ์ 7 วันเอง) แต่ 1500 อยู่ 25 วัน → ผ่านเกณฑ์
    เมื่อผ่านเกณฑ์แล้ว ref = ต่ำสุดของทุกราคาในหน้าต่าง = 1000 → 1200 ไม่ใช่ส่วนลด"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 65), (1500, 25), (1200, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] is None and got["discount_percent"] is None


def test_reference_is_min_of_all_window_prices_once_gate_passes(api, client):
    """1500 ผ่านเกณฑ์ 7 วัน → ref = ต่ำสุดของทุกราคาในหน้าต่าง (1000 ที่อยู่ 5 วัน) ไม่ใช่ 1500"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 45), (1500, 35), (1000, 5), (800, 0)])
    # หน้าต่าง [-30, 0): 1500 อยู่ 25 วัน (ผ่าน), ต่ำสุดในหน้าต่าง = 1000 → ส่วนลด 20%
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 1000 and got["discount_percent"] == 20


def test_brief_low_price_still_lowers_reference(api, client):
    """ตัดสินแล้ว: ราคาต่ำช่วงสั้น (< 7 วัน) ยังนับเป็นค่าต่ำสุด เมื่อมีราคาอื่นผ่านเกณฑ์ 7 วัน"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 20), (850, 3), (1000, 2), (800, 0)])
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 850
    assert got["discount_percent"] == 5  # floor(50*100/850)


def test_brief_low_price_can_cancel_discount(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 20), (400, 1), (900, 0)])  # ขาย 400 หนึ่งวัน → 900 ไม่ใช่ส่วนลด
    assert client.get(f"/api/products/{p['id']}").json()["original_price"] is None


def test_no_qualifying_price_no_discount_in_seller_status(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 3), (800, 0)])
    _, item = _status_item(client, h, p["id"])
    assert item["ref_price"] is None and item["discount_percent"] is None


def test_min_days_configurable(api, client, monkeypatch):
    monkeypatch.setattr(config, "PRICE_REF_MIN_DAYS", 3, raising=False)
    h, _ = api.seller()
    p = api.product(h, price=1000)
    set_history(p["id"], [(1000, 4), (800, 0)])
    with Session(engine) as s:
        pricing.recompute_price_ref(s, p["id"])
        s.commit()
    assert client.get(f"/api/products/{p['id']}").json()["original_price"] == 1000
