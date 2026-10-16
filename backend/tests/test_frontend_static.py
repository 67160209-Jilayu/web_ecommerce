"""ตรวจ frontend แบบ static: ทุกหน้าโหลดได้ และเรียก endpoint เฟส 1 ตามที่ตกลงกัน (ไม่ได้รันเบราว์เซอร์จริง)"""
import re

import pytest

PAGES = [
    "/", "/pages/cart.html", "/pages/checkout.html", "/pages/login.html", "/pages/orders.html",
    "/pages/product-detail.html", "/pages/product-form.html", "/pages/seller.html", "/pages/shop.html",
    "/js/api.js", "/css/style.css",
]


@pytest.mark.parametrize("path", PAGES)
def test_page_served(client, path):
    r = client.get(path)
    assert r.status_code == 200, path


def test_api_js_uses_agreed_endpoints(client):
    js = client.get("/js/api.js").text
    assert '"/account/notices"' in js
    assert '"/account/notices/read"' in js and 'method: "PATCH"' in js
    assert '"/seller/price-status"' in js
    # notice ต้องได้ผ่าน GET /cart พร้อม Authorization (apiFetch แนบ Bearer ให้ทุก request)
    assert "Authorization" in js and "Bearer" in js


def test_product_form_has_no_original_price_input(client):
    html = client.get("/pages/product-form.html").text
    assert not re.search(r'<input[^>]*(id|name)="original[_-]?price"', html, re.I)
    assert not re.search(r"original_price\s*:\s*(Number|parseInt|\+)", html)


def test_buyer_pages_have_no_price_history_ui(client):
    for path in ("/", "/pages/product-detail.html", "/pages/shop.html", "/pages/cart.html", "/js/api.js"):
        text = client.get(path).text.lower()
        for word in ("price-history", "price_history", "pricehistory", "min_30d", "chart.js"):
            assert word not in text, (path, word)


def test_cart_page_marks_notices_read_and_dot_logic(client):
    cart = client.get("/pages/cart.html").text
    assert "price-notices" in cart and "markNoticesRead" in cart
    js = client.get("/js/api.js").text
    assert "cart-dot" in js


def _route_patterns(app):
    pats = []
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", None) or set()
        if not path.startswith("/api/"):
            continue
        rx = "^" + re.sub(r"\{[^}]+\}", "[^/]+", path) + "$"
        pats.append((re.compile(rx), methods))
    return pats


def _js_api_calls(js):
    """ดึง (method, path) จาก apiFetch(`/...`) / apiFetch("/...") ใน api.js"""
    calls = []
    for m in re.finditer(r'apiFetch\(\s*([`"\'])(/[^`"\']*)\1(\s*,\s*\{[^}]*?method:\s*"(\w+)")?', js):
        path = m.group(2)
        path = re.sub(r"\$\{[^}`]*\}", "X", path)
        path = path.split("${")[0].split("?")[0]  # ${cond ? `?q=..` : ""} ซ้อน → ตัดส่วน query ทิ้ง
        calls.append(((m.group(4) or "GET").upper(), "/api" + path))
    return calls


def test_every_api_js_endpoint_exists_in_backend(client):
    js = client.get("/js/api.js").text
    pats = _route_patterns(client.app)
    calls = _js_api_calls(js)
    assert len(calls) > 20
    missing = []
    for method, path in calls:
        if not any(rx.match(path) and method in ms for rx, ms in pats):
            missing.append(f"{method} {path}")
    assert not missing, f"frontend เรียก endpoint ที่ backend ไม่มี: {missing}"


def test_compare_page_and_tray(client):
    html = client.get("/pages/compare.html").text
    assert "ร้านไม่ได้ระบุ" in html and "diff" in html.lower()
    js = client.get("/js/api.js").text
    assert "compare.html?ids=" in js  # ลิงก์แชร์
    assert "/account/compare-list" in js
    assert re.search(r"COMPARE_MAX\s*=\s*[2-4]", js)


def test_phase2_ui_hooks_present(client):
    js = client.get("/js/api.js").text
    assert "compare-btn" in js and "shopmarket_compare_items" in js
    assert "ข้อมูลครบ" in js or "ข้อมูลครบ" in client.get("/").text
    detail = client.get("/pages/product-detail.html").text
    for el in ("specs-content", "same-model-content", "compare-similar-btn"):
        assert el in detail, el
    form = client.get("/pages/product-form.html").text
    assert "attr-" in form and "/attributes" in js
    for f in ("brand", "model_code", "barcode"):
        assert f in form, f
    assert "shipping-form" in client.get("/pages/seller.html").text
    checkout = client.get("/pages/checkout.html").text
    assert 'id="province"' in checkout


# ------------------------------------------------------------------ เฟส 3 UI

def test_chat_policy_page(client):
    r = client.get("/pages/chat-policy.html")
    assert r.status_code == 200
    assert "ไม่มีการจ่ายเงินเพื่อให้ถูกแนะนำ" in r.text


def test_chat_js_loaded_on_entry_pages_and_uses_endpoints(client):
    for page in ("/", "/pages/product-detail.html", "/pages/compare.html"):
        assert re.search(r'<script[^>]+src="[^"]*js/chat\.js(\?v=[\w.-]+)?"', client.get(page).text), page
    js = client.get("/js/chat.js").text
    for ep in ("/chat", "/chat/config", "/chat/guided", "/chat/feedback"):
        assert ep in js, ep
    assert "text/event-stream" in js or "getReader" in js  # อ่าน SSE แบบ stream
    assert "aria-live" in js  # ข้อความ stream อ่านออกเสียงได้
    assert "ถามผู้ช่วย" in js or "ถามผู้ช่วย" in client.get("/").text


def test_chat_js_endpoints_exist(client):
    pats = _route_patterns(client.app)
    js = client.get("/js/chat.js").text
    for method, path in _js_api_calls(js) or []:
        assert any(rx.match(path) and method in ms for rx, ms in pats), f"{method} {path}"
    for path in ("/api/chat", "/api/chat/config", "/api/chat/guided", "/api/chat/feedback"):
        assert any(rx.match(path) for rx, _ in pats), path


@pytest.mark.parametrize("page", ["/", "/pages/cart.html", "/pages/checkout.html", "/pages/compare.html",
                                  "/pages/login.html", "/pages/orders.html", "/pages/product-detail.html",
                                  "/pages/product-form.html", "/pages/seller.html", "/pages/shop.html",
                                  "/pages/chat-policy.html"])
def test_skip_link_on_every_page(client, page):
    assert "skip-link" in client.get(page).text, page


def test_form_helpers_present(client):
    js = client.get("/js/api.js").text
    for fn in ("validateRequired", "setFieldError", "showToast"):
        assert f"function {fn}" in js or f"{fn} =" in js, fn
