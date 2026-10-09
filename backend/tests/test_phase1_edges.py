"""เฟส 1 — กรณีขอบที่ไม่ได้อยู่ในกฎหลักโดยตรง"""
import uuid

from sqlmodel import Session, select

from app import config, models, pricing
from app.database import engine


def _notices(client, h, include_read=False):
    url = "/api/account/notices" + ("?include_read=true" if include_read else "")
    return client.get(url, headers=h).json()


def _buyer_with_item(api, hs, pid):
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, pid, h=hb)
    return hb, token


def test_deactivated_product_removes_notice(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    hb, token = _buyer_with_item(api, hs, p["id"])
    api.set_price(hs, p["id"], 800)
    assert _notices(client, hb)["unread_count"] == 1
    assert client.delete(f"/api/products/{p['id']}", headers=hs).status_code == 204
    assert _notices(client, hb, include_read=True)["notices"] == []
    assert client.get(f"/api/cart/{token}", headers=hb).json()["notices"] == []


def test_nightly_does_not_resurrect_read_notice(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    hb, _ = _buyer_with_item(api, hs, p["id"])
    api.set_price(hs, p["id"], 800)
    client.patch("/api/account/notices/read", json={}, headers=hb)
    with Session(engine) as s:
        pricing.nightly_recompute(s)
    assert _notices(client, hb)["unread_count"] == 0
    assert len(_notices(client, hb, include_read=True)["notices"]) == 1


def test_many_buyers_each_get_own_notice(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000, stock=20)
    buyers = [_buyer_with_item(api, hs, p["id"])[0] for _ in range(3)]
    api.set_price(hs, p["id"], 800)
    for hb in buyers:
        data = _notices(client, hb)
        assert data["unread_count"] == 1 and data["notices"][0]["new_price"] == 800


def test_price_at_add_differs_per_buyer(api, client):
    """คนที่ใส่ตะกร้าตอนราคาถูกแล้วไม่ควรได้ notice เมื่อราคาลดกลับไปที่เดิม"""
    hs, _ = api.seller()
    p = api.product(hs, price=1000, stock=20)
    early, _ = _buyer_with_item(api, hs, p["id"])
    api.set_price(hs, p["id"], 900)
    late, _ = _buyer_with_item(api, hs, p["id"])
    api.set_price(hs, p["id"], 890)
    assert _notices(client, early)["notices"][0]["new_price"] == 890
    assert _notices(client, late)["unread_count"] == 0  # ลดแค่ 10 บาท (1.1%)


def test_raise_rule_via_api_only_outside_grace(api, client, monkeypatch, instant_ref):
    """ขึ้น 20% แล้วลด ภายในวันเดียว (ผ่าน API จริง ไม่ backdate)"""
    monkeypatch.setattr(config, "PRICE_GRACE_ENABLED", False)
    h, _ = api.seller()
    p = api.product(h, price=100)
    api.set_price(h, p["id"], 120)
    api.set_price(h, p["id"], 80)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 100 and got["discount_percent"] is None


def test_discount_percent_floor_and_min_1(api, client, instant_ref):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 995)  # 0.5% → ไม่แสดง %
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["discount_percent"] is None
    p2 = api.product(h, price=1000)
    api.set_price(h, p2["id"], 989)  # 1.1% → floor = 1
    assert client.get(f"/api/products/{p2['id']}").json()["discount_percent"] == 1


def test_merge_guest_into_existing_user_cart_keeps_single_notice(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000, stock=20)
    hb = api.user()
    user_token = api.user_cart(hb)
    api.add_to_cart(user_token, p["id"], h=hb)
    guest = uuid.uuid4().hex
    api.add_to_cart(guest, p["id"])
    assert client.post(f"/api/cart/{guest}/merge", headers=hb).status_code == 200
    api.set_price(hs, p["id"], 800)
    data = _notices(client, hb, include_read=True)
    assert len(data["notices"]) == 1


def test_one_open_history_row_after_many_ops(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000, stock=3)
    for body in ({"price": 900}, {"stock": 0}, {"price": 950}, {"stock": 2}, {"price": 950}):
        assert client.patch(f"/api/products/{p['id']}", json=body, headers=hs).status_code == 200
    with Session(engine) as s:
        rows = s.exec(select(models.SkuPriceHistory).where(models.SkuPriceHistory.sku_id == p["id"])).all()
    assert len(rows) == 5  # สร้าง + 4 การเปลี่ยนจริง (ราคา 950 ซ้ำไม่นับ)
    assert sum(1 for r in rows if r.valid_to is None) == 1
