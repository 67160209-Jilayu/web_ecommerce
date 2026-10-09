"""เฟส 1 — ราคาก่อนลดที่ระบบคำนวณ, การไม่เปิดเผยประวัติราคา, และ GET /api/seller/price-status"""
import json
import uuid

# คำที่ห้ามโผล่ใน response ของ endpoint สาธารณะ (ข้อมูลประวัติราคาเป็นของภายในเท่านั้น)
FORBIDDEN_KEYS = (
    "history", "price_history", "valid_from", "valid_to", "min_30d",
    "max_increase_14d", "price_type", "sku_price", "effective_price", "list_price",
)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _assert_no_history(payload):
    keys = set(_keys(payload))
    leaked = [k for k in keys if any(f in k.lower() for f in FORBIDDEN_KEYS)]
    assert not leaked, f"ข้อมูลประวัติราคาหลุดออก endpoint สาธารณะ: {leaked}"


# ------------------------------------------------------------ original_price

def test_seller_typed_original_price_is_ignored(api, client):
    h, _ = api.seller()
    p = api.product(h, price=500, original_price=9999)
    assert p["original_price"] is None
    assert p.get("discount_percent") is None
    p2 = client.patch(f"/api/products/{p['id']}", json={"original_price": 8888}, headers=h)
    assert p2.status_code == 200
    assert p2.json()["original_price"] is None
    assert client.get(f"/api/products/{p['id']}").json()["original_price"] is None


def test_price_drop_shows_system_reference_price(api, client, instant_ref):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 800)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["price"] == 800
    assert got["original_price"] == 1000
    assert got["discount_percent"] == 20


def test_reference_is_lowest_price_not_highest(api, client, instant_ref):
    """1000 → 900 → 1200 → 850: ราคาก่อนลด = ต่ำสุดใน 30 วัน = 900 (ไม่ใช่ 1200)"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    for price in (900, 1200, 850):
        api.set_price(h, p["id"], price)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] == 900


def test_raise_is_not_a_discount(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 1100)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] is None and got["discount_percent"] is None


def test_back_to_old_price_is_not_a_discount(api, client):
    """1000 → 800 → 1000 → 900: ต่ำสุดใน 30 วันคือ 800 → 900 ไม่ใช่ส่วนลด"""
    h, _ = api.seller()
    p = api.product(h, price=1000)
    for price in (800, 1000, 900):
        api.set_price(h, p["id"], price)
    got = client.get(f"/api/products/{p['id']}").json()
    assert got["original_price"] is None


def test_reference_price_consistent_across_listing_endpoints(api, client, instant_ref):
    h, shop = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 700)
    lists = [
        client.get("/api/products").json(),
        client.get(f"/api/shops/{shop['id']}/products").json(),
        client.get("/api/products/me", headers=h).json(),
    ]
    for lst in lists:
        item = next(x for x in lst if x["id"] == p["id"])
        assert item["original_price"] == 1000 and item["discount_percent"] == 30


# ------------------------------------------------------------ no history exposure

def test_public_endpoints_never_expose_history(api, client):
    h, shop = api.seller()
    p = api.product(h, price=1000)
    for price in (900, 1100, 800):
        api.set_price(h, p["id"], price)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)

    for url, headers in [
        ("/api/products", {}),
        (f"/api/products/{p['id']}", {}),
        (f"/api/shops/{shop['id']}/products", {}),
        (f"/api/shops/{shop['id']}", {}),
        (f"/api/cart/{token}", hb),
        ("/api/account/notices?include_read=true", hb),
    ]:
        r = client.get(url, headers=headers)
        assert r.status_code == 200, (url, r.text)
        _assert_no_history(r.json())


def test_no_public_route_for_price_history(client):
    paths = [getattr(r, "path", "") for r in client.app.routes]
    assert not [p for p in paths if "history" in p.lower()], paths
    spec = json.dumps(client.get("/openapi.json").json()["paths"])
    assert "history" not in spec.lower()


# ------------------------------------------------------------ seller price-status

def test_price_status_requires_auth(client):
    assert client.get("/api/seller/price-status").status_code == 401


def test_price_status_requires_shop(api, client):
    h = api.user()
    assert client.get("/api/seller/price-status", headers=h).status_code == 400


def test_price_status_shape_and_rules(api, client, instant_ref):
    h, _ = api.seller()
    p = api.product(h, price=1000)
    api.set_price(h, p["id"], 800)
    r = client.get("/api/seller/price-status", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["grace"]) >= {"enabled", "active", "starts_at", "ends_at"}
    assert body["rules"] == {
        "ref_window_days": 30, "raise_window_days": 14, "raise_percent": 15,
        "notice_min_percent": 3, "notice_min_baht": 20,
    }
    item = next(i for i in body["items"] if i["product_id"] == p["id"])
    for key in ("name", "is_active", "price", "in_stock", "ref_price", "min_30d",
                "discount_percent", "discount_hidden", "max_increase_14d_percent",
                "warnings", "carts_holding", "carts_notice_eligible", "ref_updated_at"):
        assert key in item, key
    assert item["price"] == 800 and item["ref_price"] == 1000 and item["min_30d"] == 1000
    assert item["discount_percent"] == 20 and item["discount_hidden"] is False
    assert item["in_stock"] is True


def test_price_status_only_own_shop(api, client):
    h1, shop1 = api.seller()
    h2, shop2 = api.seller()
    p1 = api.product(h1, name="ของร้าน 1")
    p2 = api.product(h2, name="ของร้าน 2")
    items = client.get("/api/seller/price-status", headers=h1).json()["items"]
    ids = {i["product_id"] for i in items}
    assert p1["id"] in ids and p2["id"] not in ids
    # พยายามขอข้อมูลร้านอื่นผ่าน query → ต้อง 403 หรือไม่สนใจ param แล้วคืนของร้านตัวเอง
    for q in (f"shop_id={shop2['id']}", f"product_id={p2['id']}"):
        r = client.get(f"/api/seller/price-status?{q}", headers=h1)
        if r.status_code == 200:
            ids = {i["product_id"] for i in r.json()["items"]}
            assert p2["id"] not in ids, q
        else:
            assert r.status_code == 403, (q, r.status_code)


def test_price_status_cart_counts_anonymous(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000, stock=50)
    # 2 ตะกร้าล็อกอิน + 1 ตะกร้า guest
    for _ in range(2):
        hb = api.user()
        api.add_to_cart(api.user_cart(hb), p["id"], h=hb)
    api.add_to_cart(uuid.uuid4().hex, p["id"])
    item = next(i for i in client.get("/api/seller/price-status", headers=h).json()["items"]
                if i["product_id"] == p["id"])
    assert item["carts_holding"] == 3
    assert item["carts_notice_eligible"] == 2
    # ต้องไม่บอกว่าใครถือสินค้าไว้
    text = json.dumps(item).lower()
    assert "email" not in text and "user_id" not in text and "token" not in text


def test_price_status_includes_inactive_and_out_of_stock(api, client):
    h, _ = api.seller()
    p = api.product(h, price=1000, stock=1)
    client.patch(f"/api/products/{p['id']}", json={"stock": 0}, headers=h)
    item = next(i for i in client.get("/api/seller/price-status", headers=h).json()["items"]
                if i["product_id"] == p["id"])
    assert item["in_stock"] is False
