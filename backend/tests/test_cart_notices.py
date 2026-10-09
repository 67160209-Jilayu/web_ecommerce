"""เฟส 1 — notice ราคาลดในตะกร้า (cart_price_notice) ตาม contract ใน team-log

กฎ: เฉพาะผู้ใช้ล็อกอิน; ราคาตอนนี้ต่ำกว่า price_at_add ≥ 3% หรือ ≥ 20 บาท;
ลดอีก → อัปเดตแถวเดิม; ราคาขึ้นจนไม่เข้าเงื่อนไข → ลบ; หายเมื่อเปิดดู (PATCH read) หรือเอาออก
"""
import uuid

import pytest

CHECKOUT_BODY = {
    "recipient_name": "ผู้รับ",
    "recipient_phone": "0800000000",
    "address": "กรุงเทพฯ",
    "payment_method": "COD",
}


@pytest.fixture
def setup(api):
    """ผู้ขาย 1 ร้าน + ผู้ซื้อที่ล็อกอิน พร้อมตะกร้าที่ผูกบัญชีแล้ว"""
    hs, shop = api.seller()
    hb = api.user()
    token = api.user_cart(hb)
    return hs, hb, token


def _cart(client, token, h=None):
    r = client.get(f"/api/cart/{token}", headers=h or {})
    assert r.status_code == 200, r.text
    return r.json()


def _notices(client, h, include_read=False):
    url = "/api/account/notices" + ("?include_read=true" if include_read else "")
    r = client.get(url, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_cart_item_has_price_at_add_and_id(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    item = _cart(client, token, hb)["items"][0]
    assert item["price_at_add"] == 1000
    assert isinstance(item["cart_item_id"], int)


def test_no_notice_when_drop_below_both_thresholds(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 981)  # ลด 19 บาท = 1.9%
    assert _cart(client, token, hb)["notices"] == []
    assert _notices(client, hb)["unread_count"] == 0


def test_notice_by_baht_threshold(api, client, setup):
    """1000 → 980: ลด 20 บาท (2%) — ผ่านเกณฑ์ 20 บาท แม้ไม่ถึง 3%"""
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 980)
    notices = _cart(client, token, hb)["notices"]
    assert len(notices) == 1
    n = notices[0]
    assert n["old_price"] == 1000 and n["new_price"] == 980
    assert n["sku_id"] == p["id"] and n["product_id"] == p["id"]
    assert n["read_at"] is None
    for key in ("id", "cart_item_id", "product_name", "image", "cover_url", "created_at"):
        assert key in n


def test_notice_by_percent_threshold(api, client, setup):
    """500 → 485: ลด 15 บาท = 3% — ผ่านเกณฑ์ 3% แม้ไม่ถึง 20 บาท"""
    hs, hb, token = setup
    p = api.product(hs, price=500)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 486)  # 2.8%, 14 บาท → ยังไม่ถึง
    assert _cart(client, token, hb)["notices"] == []
    api.set_price(hs, p["id"], 485)
    notices = _cart(client, token, hb)["notices"]
    assert len(notices) == 1 and notices[0]["new_price"] == 485


def test_further_drop_updates_same_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 900)
    first = _notices(client, hb)["notices"]
    api.set_price(hs, p["id"], 800)
    data = _notices(client, hb, include_read=True)
    assert len(data["notices"]) == 1
    assert data["notices"][0]["id"] == first[0]["id"]
    assert data["notices"][0]["new_price"] == 800
    assert data["notices"][0]["old_price"] == 1000


def test_further_drop_after_read_shows_again(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 900)
    r = client.patch("/api/account/notices/read", json={}, headers=hb)
    assert r.status_code == 204
    assert _notices(client, hb)["unread_count"] == 0
    api.set_price(hs, p["id"], 850)
    data = _notices(client, hb)
    assert data["unread_count"] == 1 and data["notices"][0]["new_price"] == 850


def test_rise_still_qualifying_updates_price(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    api.set_price(hs, p["id"], 900)  # ขึ้น แต่ยังต่ำกว่าตอนใส่ตะกร้า ≥ เกณฑ์
    n = _notices(client, hb, include_read=True)["notices"]
    assert len(n) == 1 and n[0]["new_price"] == 900


def test_rise_out_of_threshold_deletes_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    api.set_price(hs, p["id"], 990)  # ลดแค่ 10 บาท/1% → ไม่เข้าเงื่อนไขแล้ว
    assert _notices(client, hb, include_read=True)["notices"] == []


def test_rise_above_price_at_add_deletes_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    api.set_price(hs, p["id"], 1200)
    assert _notices(client, hb, include_read=True)["notices"] == []
    assert _cart(client, token, hb)["notices"] == []


def test_mark_read_by_ids_clears_from_unread(api, client, setup):
    hs, hb, token = setup
    p1 = api.product(hs, price=1000, name="A")
    p2 = api.product(hs, price=1000, name="B")
    api.add_to_cart(token, p1["id"], h=hb)
    api.add_to_cart(token, p2["id"], h=hb)
    api.set_price(hs, p1["id"], 800)
    api.set_price(hs, p2["id"], 800)
    data = _notices(client, hb)
    assert data["unread_count"] == 2
    first_id = data["notices"][0]["id"]
    r = client.patch("/api/account/notices/read", json={"ids": [first_id]}, headers=hb)
    assert r.status_code == 204
    data = _notices(client, hb)
    assert data["unread_count"] == 1 and all(n["id"] != first_id for n in data["notices"])
    assert all(n["id"] != first_id for n in _cart(client, token, hb)["notices"])
    # include_read ยังเห็นตัวที่อ่านแล้ว
    assert len(_notices(client, hb, include_read=True)["notices"]) == 2


def test_cannot_mark_other_users_notice_read(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    nid = _notices(client, hb)["notices"][0]["id"]
    other = api.user()
    client.patch("/api/account/notices/read", json={"ids": [nid]}, headers=other)
    assert _notices(client, hb)["unread_count"] == 1


def test_removing_item_deletes_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    assert _notices(client, hb)["unread_count"] == 1
    r = client.delete(f"/api/cart/{token}/items/{p['id']}")
    assert r.status_code == 200
    assert _notices(client, hb, include_read=True)["notices"] == []


def test_quantity_zero_deletes_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    client.patch(f"/api/cart/{token}/items/{p['id']}", json={"quantity": 0})
    assert _notices(client, hb, include_read=True)["notices"] == []


def test_checkout_deletes_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    r = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT_BODY, headers=hb)
    assert r.status_code == 201, r.text
    assert _notices(client, hb, include_read=True)["notices"] == []


def test_guest_cart_never_gets_notice(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    token = uuid.uuid4().hex
    api.add_to_cart(token, p["id"])
    api.set_price(hs, p["id"], 500)
    assert _cart(client, token)["notices"] == []


def test_guest_cart_after_login_merge_starts_fresh(api, client):
    """ตะกร้า guest ที่ราคาลดไปก่อนล็อกอิน → ผูกบัญชีแล้วต้องไม่ error; notice ใหม่เกิดเมื่อราคาเปลี่ยนต่อจากนี้"""
    hs, _ = api.seller()
    p = api.product(hs, price=1000)
    token = uuid.uuid4().hex
    api.add_to_cart(token, p["id"])
    hb = api.user()
    r = client.post(f"/api/cart/{token}/merge", headers=hb)
    assert r.status_code == 200
    api.set_price(hs, p["id"], 800)
    n = _notices(client, hb)["notices"]
    assert len(n) == 1 and n[0]["old_price"] == 1000


def test_other_user_sees_no_notices_on_someone_elses_cart(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    api.set_price(hs, p["id"], 800)
    other = api.user()
    assert _cart(client, token, other)["notices"] == []
    assert _cart(client, token)["notices"] == []  # ไม่ส่ง token ก็ไม่เห็น
    assert _notices(client, other)["unread_count"] == 0


def test_one_notice_per_cart_item_over_many_changes(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    for price in (950, 900, 960, 850, 800, 700):
        api.set_price(hs, p["id"], price)
    n = _notices(client, hb, include_read=True)["notices"]
    assert len(n) == 1 and n[0]["new_price"] == 700


def test_unrelated_edit_does_not_create_notice(api, client, setup):
    hs, hb, token = setup
    p = api.product(hs, price=1000)
    api.add_to_cart(token, p["id"], h=hb)
    r = client.patch(f"/api/products/{p['id']}", json={"name": "ชื่อใหม่", "description": "x"}, headers=hs)
    assert r.status_code == 200
    assert _notices(client, hb)["unread_count"] == 0


def test_notices_require_auth(client):
    assert client.get("/api/account/notices").status_code == 401
    assert client.patch("/api/account/notices/read", json={}).status_code == 401
