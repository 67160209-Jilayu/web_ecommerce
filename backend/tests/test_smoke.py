"""Smoke test ของ flow เดิมก่อนเฟส 1 — กัน regression"""
import uuid

CHECKOUT_BODY = {
    "recipient_name": "ผู้รับ",
    "recipient_phone": "0800000000",
    "address": "กรุงเทพฯ",
    "payment_method": "COD",
}


def test_health_and_frontend(client):
    assert client.get("/api/health").json()["status"] == "ok"
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()


def test_seed_categories_and_mango(client):
    cats = client.get("/api/categories").json()
    assert len(cats) == 6
    r = client.post("/api/auth/login", data={"username": "mango@shopmarket.test", "password": "mango1234"})
    assert r.status_code == 200


def test_register_login_me(api, client):
    h, _, email = api.register_login()
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["email"] == email


def test_register_duplicate_email(api, client):
    _, _, email = api.register_login()
    r = client.post("/api/auth/register", json={"email": email, "password": "x", "name": "y"})
    assert r.status_code == 400


def test_login_wrong_password(api, client):
    _, _, email = api.register_login()
    r = client.post("/api/auth/login", data={"username": email, "password": "wrong"})
    assert r.status_code == 401


def test_product_create_update_and_public_read(api, client):
    h, shop = api.seller()
    p = api.product(h, price=500, stock=3)
    assert p["price"] == 500 and p["shop_id"] == shop["id"]
    api.set_price(h, p["id"], 450)
    assert client.get(f"/api/products/{p['id']}").json()["price"] == 450
    assert any(x["id"] == p["id"] for x in client.get("/api/products").json())


def test_cannot_edit_other_shop_product(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    p = api.product(h1)
    r = client.patch(f"/api/products/{p['id']}", json={"price": 1}, headers=h2)
    assert r.status_code == 403


def test_guest_cart_add_update_remove(api, client):
    h, _ = api.seller()
    p = api.product(h, price=100, stock=5)
    token = uuid.uuid4().hex
    cart = api.add_to_cart(token, p["id"], 2)
    assert cart["total"] == 200
    r = client.patch(f"/api/cart/{token}/items/{p['id']}", json={"quantity": 99})
    assert r.status_code == 200 and r.json()["items"][0]["quantity"] == 5  # cap ที่ stock
    r = client.delete(f"/api/cart/{token}/items/{p['id']}")
    assert r.status_code == 200 and r.json()["items"] == []


def test_cannot_buy_own_product(api, client):
    h, _ = api.seller()
    p = api.product(h)
    r = client.post(f"/api/cart/{uuid.uuid4().hex}/items", json={"product_id": p["id"], "quantity": 1}, headers=h)
    assert r.status_code == 400


def test_checkout_flow_and_order_price_snapshot(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=300, stock=2)
    hb = api.user()
    token = uuid.uuid4().hex
    api.add_to_cart(token, p["id"], 2, h=hb)
    client.post(f"/api/cart/{token}/merge", headers=hb)
    r = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT_BODY, headers=hb)
    assert r.status_code == 201, r.text
    orders = r.json()
    assert len(orders) == 1 and orders[0]["subtotal"] == 600 and orders[0]["status"] == "PAID"
    assert client.get(f"/api/products/{p['id']}").json()["stock"] == 0

    # ร้านขึ้นราคาหลังสั่ง → ออเดอร์ใช้ราคา snapshot
    api.set_price(hs, p["id"], 999)
    o = client.get(f"/api/orders/{orders[0]['id']}", headers=hb).json()
    assert o["subtotal"] == 600

    # ยกเลิก → คืน stock
    r = client.post(f"/api/orders/{orders[0]['id']}/cancel", headers=hb)
    assert r.status_code == 200, r.text
    assert client.get(f"/api/products/{p['id']}").json()["stock"] == 2


def test_checkout_insufficient_stock(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=300, stock=1)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], 1, h=hb)
    # ร้านลด stock เหลือ 0 หลังลูกค้าใส่ตะกร้า
    r = client.patch(f"/api/products/{p['id']}", json={"stock": 0}, headers=hs)
    assert r.status_code == 200
    r = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT_BODY, headers=hb)
    assert r.status_code == 400
