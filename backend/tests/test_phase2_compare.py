"""เฟส 2 — แม่แบบสเปก, ค่าสเปกสินค้า, AI เสนอสเปก, ค่าส่ง, หน้าเทียบ, ร้านอื่นที่ขายรุ่นนี้, ถาดเทียบ, ranking

อ้างอิง contract "[backend] Phase 2 contract" ใน team-log — เทสต์อ่านแม่แบบจาก API จริง
จึงไม่ผูกกับชื่อ key ที่ backend seed ไว้
"""
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

from tests.test_price_api import _assert_no_history

CHECKOUT = {"recipient_name": "ผู้รับ", "recipient_phone": "0800000000",
            "address": "123 ถนนสุขุมวิท กรุงเทพมหานคร", "payment_method": "COD"}


# ------------------------------------------------------------------ helpers

def cat_id(client, slug):
    return next(c["id"] for c in client.get("/api/categories").json() if c["slug"] == slug)


def attrs(client, cid):
    r = client.get(f"/api/categories/{cid}/attributes")
    assert r.status_code == 200, r.text
    return r.json()


def sample_value(a, n=10):
    """ค่าที่ถูกต้องตามชนิดข้อมูลของ attribute"""
    if a["data_type"] == "number":
        return {"key": a["key"], "value_num": n}
    if a["data_type"] == "enum":
        return {"key": a["key"], "value_text": a["options"][0]}
    if a["data_type"] == "bool":
        return {"key": a["key"], "value_num": 1}
    return {"key": a["key"], "value_text": "ทดสอบ"}


def required_values(client, cid):
    return [sample_value(a) for a in attrs(client, cid) if a["required"]]


def number_attr(client, cid, better="higher"):
    for a in attrs(client, cid):
        if a["data_type"] == "number" and a["better"] == better:
            return a
    pytest.skip(f"category {cid} has no number attr with better={better}")


def make_product(api, h, client, slug="electronics", price=1000, values=None, **kw):
    cid = cat_id(client, slug)
    body = {"category_id": cid, "attributes": values if values is not None else []}
    body.update(kw)
    return api.product(h, price=price, **body)


def reviewed(api, client, hs, pid, rating):
    """ซื้อจริง → ส่ง → รับ → รีวิว"""
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, pid, h=hb)
    order = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT, headers=hb).json()[0]
    assert client.post(f"/api/orders/{order['id']}/ship", headers=hs).status_code == 200
    assert client.post(f"/api/orders/{order['id']}/receive", headers=hb).status_code == 200
    r = client.post("/api/reviews", json={"order_item_id": order["items"][0]["id"], "rating": rating}, headers=hb)
    assert r.status_code == 201, r.text


def compare(client, ids, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/compare?ids={','.join(map(str, ids))}" + (f"&{q}" if q else ""))
    return r


def all_rows(body):
    return [row for g in body["groups"] for row in g["rows"]]


# ================================================================== templates

SLUGS = ["home", "kitchen", "beauty", "electronics", "fashion", "sports"]


@pytest.mark.parametrize("slug", SLUGS)
def test_category_template_shape(client, slug):
    a = attrs(client, cat_id(client, slug))
    assert 8 <= len(a) <= 15, (slug, len(a))
    keys = [x["key"] for x in a]
    assert len(keys) == len(set(keys))
    assert any(x["required"] for x in a)
    for x in a:
        assert set(x) >= {"key", "name_th", "unit", "data_type", "options", "group_name",
                          "better", "required", "sort", "badge_label"}
        assert x["data_type"] in ("number", "text", "enum", "bool")
        assert x["better"] in ("higher", "lower", "none")
        assert x["group_name"]
        if x["data_type"] == "enum":
            assert x["options"], x["key"]


def test_template_seed_idempotent(client):
    before = {s: len(attrs(client, cat_id(client, s))) for s in SLUGS}
    with TestClient(app) as c2:  # startup รอบสอง (upsert ซ้ำ)
        after = {s: len(attrs(c2, cat_id(c2, s))) for s in SLUGS}
    assert before == after


def test_unknown_category_attributes(client):
    r = client.get("/api/categories/99999/attributes")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.json() == []


# ================================================================== product attributes

def test_create_with_attributes_and_codes(api, client):
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    vals = required_values(client, cid)
    p = make_product(api, h, client, values=vals, brand="Sony", model_code="WH-1000XM5", barcode="4548736132610")
    assert p["brand"] == "Sony" and p["model_code"] == "WH-1000XM5" and p["barcode"] == "4548736132610"
    got = {a["key"]: a for a in p["attributes"]}
    assert set(got) == {v["key"] for v in vals}
    for a in got.values():
        assert a["source"] == "seller" and a["display"]
        assert set(a) >= {"key", "name_th", "unit", "group_name", "data_type", "value_num", "value_text", "display", "source"}
    assert p["spec_complete"] is True
    assert client.get(f"/api/products/{p['id']}").json()["spec_complete"] is True


def test_spec_complete_false_when_required_missing(api, client):
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    vals = required_values(client, cid)
    if len(vals) < 1:
        pytest.skip("no required attrs")
    p = make_product(api, h, client, values=vals[:-1])
    assert p["spec_complete"] is False


def test_spec_complete_false_without_category(api, client):
    h, _ = api.seller()
    p = api.product(h, price=100)
    assert p["spec_complete"] is False and p["attributes"] == []


@pytest.mark.parametrize("bad", ["unknown_key", "negative", "not_numeric", "bad_enum", "long_text"])
def test_attribute_validation_400(api, client, bad):
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    a = attrs(client, cid)
    if bad == "unknown_key":
        v = {"key": "no_such_key_xyz", "value_text": "x"}
    elif bad in ("negative", "not_numeric"):
        num = next((x for x in a if x["data_type"] == "number"), None) or pytest.skip("no number attr")
        v = {"key": num["key"], "value_num": -5} if bad == "negative" else {"key": num["key"], "value_text": "ห้าพัน"}
    elif bad == "bad_enum":
        en = next((x for x in a if x["data_type"] == "enum"), None) or pytest.skip("no enum attr")
        v = {"key": en["key"], "value_text": "ไม่มีในตัวเลือก-xyz"}
    else:
        tx = next((x for x in a if x["data_type"] == "text"), None) or pytest.skip("no text attr")
        v = {"key": tx["key"], "value_text": "ก" * 101}
    r = client.post("/api/products", json={"name": "x", "price": 100, "stock": 1, "category_id": cid, "attributes": [v]}, headers=h)
    assert r.status_code == 400, (bad, r.status_code, r.text)
    assert isinstance(r.json()["detail"], str)


def test_attributes_full_replace_and_omit_keeps(api, client):
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    vals = required_values(client, cid)
    p = make_product(api, h, client, values=vals)
    r = client.patch(f"/api/products/{p['id']}", json={"price": 900}, headers=h)
    assert len(r.json()["attributes"]) == len(vals)  # ไม่ส่ง attributes = คงเดิม
    r = client.patch(f"/api/products/{p['id']}", json={"attributes": vals[:1]}, headers=h)
    assert [a["key"] for a in r.json()["attributes"]] == [vals[0]["key"]]  # ส่ง = แทนทั้งชุด
    r = client.patch(f"/api/products/{p['id']}", json={"attributes": []}, headers=h)
    assert r.json()["attributes"] == []


def test_empty_values_dropped(api, client):
    h, _ = api.seller()
    a = attrs(client, cat_id(client, "electronics"))[0]
    p = make_product(api, h, client, values=[{"key": a["key"], "value_num": None, "value_text": ""}])
    assert p["attributes"] == []


def test_changing_category_drops_foreign_attrs(api, client):
    h, _ = api.seller()
    e_vals = required_values(client, cat_id(client, "electronics"))
    p = make_product(api, h, client, values=e_vals)
    kitchen_keys = {a["key"] for a in attrs(client, cat_id(client, "kitchen"))}
    r = client.patch(f"/api/products/{p['id']}", json={"category_id": cat_id(client, "kitchen")}, headers=h)
    assert r.status_code == 200, r.text
    assert all(a["key"] in kitchen_keys for a in r.json()["attributes"])


def test_bool_attribute_stored_as_1_0(api, client):
    h, _ = api.seller()
    for slug in SLUGS:
        b = next((x for x in attrs(client, cat_id(client, slug)) if x["data_type"] == "bool"), None)
        if b:
            break
    else:
        pytest.skip("no bool attr in any category")
    p = make_product(api, h, client, slug=slug, values=[{"key": b["key"], "value_num": 0}])
    assert p["attributes"][0]["value_num"] == 0


# ================================================================== spec suggestions

def _mah_attr(client):
    cid = cat_id(client, "electronics")
    for a in attrs(client, cid):
        if a["data_type"] == "number" and (a["unit"] or "").lower() == "mah":
            return a
    pytest.skip("electronics template has no mAh attr")


def test_suggestions_noop_without_llm(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none", raising=False)
    h, _ = api.seller()
    p = make_product(api, h, client, description="แบต 5000 mAh")
    r = client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=h)
    assert r.status_code == 200 and r.json() == []


def test_suggestions_fake_provider_flow(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    mah = _mah_attr(client)
    h, _ = api.seller()
    p = make_product(api, h, client, description="ลำโพงพกพา แบต 5000 mAh กันน้ำ")
    r = client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=h)
    assert r.status_code == 200, r.text
    sug = {s["key"]: s for s in r.json()}
    assert mah["key"] in sug and sug[mah["key"]]["value_num"] == 5000
    # ไม่บันทึกค่าเองอัตโนมัติ
    assert all(a["key"] != mah["key"] for a in client.get(f"/api/products/{p['id']}").json()["attributes"])
    assert {s["key"] for s in client.get(f"/api/products/{p['id']}/spec-suggestions", headers=h).json()} == set(sug)
    # ยืนยัน → source ai_confirmed
    r = client.post(f"/api/products/{p['id']}/spec-suggestions/confirm", json={"keys": [mah["key"]]}, headers=h)
    assert r.status_code == 200, r.text
    got = next(a for a in r.json()["attributes"] if a["key"] == mah["key"])
    assert got["source"] == "ai_confirmed" and got["value_num"] == 5000
    assert mah["key"] not in {s["key"] for s in client.get(f"/api/products/{p['id']}/spec-suggestions", headers=h).json()}
    # สร้างซ้ำภายใน 24 ชม. → 429
    assert client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=h).status_code == 429


def test_suggestions_dismiss(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    mah = _mah_attr(client)
    h, _ = api.seller()
    p = make_product(api, h, client, description="แบต 5000 mAh")
    client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=h)
    r = client.post(f"/api/products/{p['id']}/spec-suggestions/dismiss", json={"keys": [mah["key"]]}, headers=h)
    assert r.status_code == 204
    assert mah["key"] not in {s["key"] for s in client.get(f"/api/products/{p['id']}/spec-suggestions", headers=h).json()}
    assert all(a["key"] != mah["key"] for a in client.get(f"/api/products/{p['id']}").json()["attributes"])


def test_suggestions_skip_filled_keys(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    mah = _mah_attr(client)
    h, _ = api.seller()
    p = make_product(api, h, client, description="แบต 5000 mAh", values=[{"key": mah["key"], "value_num": 3000}])
    r = client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=h)
    assert mah["key"] not in {s["key"] for s in r.json()}


def test_suggestions_owner_only(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    h, _ = api.seller()
    other, _ = api.seller()
    p = make_product(api, h, client, description="แบต 5000 mAh")
    assert client.get(f"/api/products/{p['id']}/spec-suggestions", headers=other).status_code == 403
    assert client.post(f"/api/products/{p['id']}/spec-suggestions/generate", headers=other).status_code == 403
    assert client.post(f"/api/products/{p['id']}/spec-suggestions/confirm", json={"keys": []}, headers=other).status_code == 403
    assert client.get(f"/api/products/{p['id']}/spec-suggestions").status_code == 401


def test_batch_never_writes_values(api, client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    from sqlmodel import Session
    from app import spec_suggest
    from app.database import engine
    h, _ = api.seller()
    p = make_product(api, h, client, description="แบต 5000 mAh หนัก 250 g")
    with Session(engine) as s:
        n1 = spec_suggest.run(s)
    with Session(engine) as s:
        n2 = spec_suggest.run(s)  # ไม่ทำซ้ำสินค้าที่มี suggestion แล้ว
    assert n1 >= 1 and n2 == 0
    assert client.get(f"/api/products/{p['id']}").json()["attributes"] == []


# ================================================================== shipping

def test_provinces_and_regions(client):
    prov = client.get("/api/shipping/provinces").json()
    assert len(prov) == 77
    names = {p["name"] for p in prov}
    assert "กรุงเทพมหานคร" in names and "เชียงใหม่" in names
    regions = client.get("/api/shipping/regions").json()
    assert {p["region"] for p in prov} <= set(regions)


def _region_of(client, province):
    return next(p["region"] for p in client.get("/api/shipping/provinces").json() if p["name"] == province)


def test_shop_shipping_defaults_and_update(api, client):
    h, _ = api.seller()
    s = client.get("/api/shops/me/shipping", headers=h).json()
    assert (s["flat_rate"], s["free_over"], s["days_min"], s["days_max"]) == (40, 500, 2, 4)
    region = _region_of(client, "เชียงใหม่")
    body = {"flat_rate": 50, "free_over": None, "days_min": 1, "days_max": 3,
            "region_rates": [{"region": region, "rate": 90, "days_min": 3, "days_max": 5}]}
    r = client.put("/api/shops/me/shipping", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["region_rates"][0]["rate"] == 90 and r.json()["free_over"] is None


def test_shop_shipping_requires_shop(api, client):
    assert client.get("/api/shops/me/shipping", headers=api.user()).status_code in (400, 404)
    assert client.get("/api/shops/me/shipping").status_code == 401


def test_account_province(api, client):
    h = api.user()
    assert client.get("/api/account/province", headers=h).json() == {"province": None, "region": None, "source": None}
    assert client.put("/api/account/province", json={"province": "แอตแลนติส"}, headers=h).status_code == 400
    r = client.put("/api/account/province", json={"province": "เชียงใหม่"}, headers=h)
    assert r.status_code == 200
    assert r.json()["province"] == "เชียงใหม่" and r.json()["source"] == "account"
    assert r.json()["region"] == _region_of(client, "เชียงใหม่")


def test_account_province_from_last_order(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=100, stock=5)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    body = dict(CHECKOUT, address="99 ถ.นิมมานเหมินท์ อ.เมือง จ.เชียงใหม่ 50200")
    assert client.post(f"/api/orders/checkout?token={token}", json=body, headers=hb).status_code == 201
    r = client.get("/api/account/province", headers=hb).json()
    assert r["province"] == "เชียงใหม่" and r["source"] == "order"


def test_checkout_default_shipping_unchanged(api, client):
    hs, _ = api.seller()
    cheap = api.product(hs, price=100, stock=5)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, cheap["id"], h=hb)
    o = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT, headers=hb).json()[0]
    assert o["shipping_fee"] == 40 and o["total"] == 140


def test_checkout_uses_region_rate(api, client):
    hs, _ = api.seller()
    region = _region_of(client, "เชียงใหม่")
    client.put("/api/shops/me/shipping", headers=hs, json={
        "flat_rate": 40, "free_over": 500, "days_min": 2, "days_max": 4,
        "region_rates": [{"region": region, "rate": 75, "days_min": 3, "days_max": 6}]})
    p = api.product(hs, price=100, stock=5)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    body = dict(CHECKOUT, province="เชียงใหม่")
    o = client.post(f"/api/orders/checkout?token={token}", json=body, headers=hb).json()[0]
    assert o["shipping_fee"] == 75


# ================================================================== compare

@pytest.fixture
def trio(api, client):
    """3 ชิ้นหมวดเดียวกัน คนละร้าน ค่าสเปก higher ต่างกัน"""
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    req = [v for v in required_values(client, cid) if v["key"] != num["key"]]
    out = []
    for price, n in ((1000, 10), (900, 20), (1100, 5)):
        h, shop = api.seller()
        p = make_product(api, h, client, price=price, values=req + [{"key": num["key"], "value_num": n}])
        out.append((h, shop, p))
    return out, num


def test_compare_basic_shape(client, trio):
    items, num = trio
    ids = [p["id"] for _, _, p in items]
    r = compare(client, ids, diff_only="false")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["same_category"] is True and b["missing_ids"] == []
    assert [i["product_id"] for i in b["items"]] == ids
    for it in b["items"]:
        assert it["shipping"] is not None and it["total"] == it["price"] + it["shipping"]["fee"]
        assert isinstance(it["badges"], list)
    _assert_no_history(b)


@pytest.mark.parametrize("ids", ["", "1,2,3,4,5"])
def test_compare_id_count_limits(client, ids):
    assert client.get(f"/api/compare?ids={ids}").status_code == 422


def test_compare_single_item_ok(api, client):
    h, _ = api.seller()
    p = make_product(api, h, client)
    assert compare(client, [p["id"]]).status_code == 200


def test_compare_missing_and_inactive(api, client):
    h, _ = api.seller()
    p1 = make_product(api, h, client)
    p2 = make_product(api, h, client)
    client.delete(f"/api/products/{p2['id']}", headers=h)
    b = compare(client, [p1["id"], p2["id"], 999999]).json()
    assert set(b["missing_ids"]) == {p2["id"], 999999}
    assert [i["product_id"] for i in b["items"]] == [p1["id"]]


def test_compare_better_value_and_unique_badge(client, trio):
    items, num = trio
    b = compare(client, [p["id"] for _, _, p in items], diff_only="true").json()
    row = next(r for r in all_rows(b) if r["key"] == num["key"])
    assert row["differs"] is True
    assert [c["is_best"] for c in row["cells"]] == [False, True, False]
    if num["badge_label"]:
        assert num["badge_label"] in b["items"][1]["badges"]
        assert all(num["badge_label"] not in i["badges"] for i in (b["items"][0], b["items"][2]))


def test_compare_lower_is_better(api, client):
    cid = cat_id(client, "electronics")
    for slug in SLUGS:
        cid = cat_id(client, slug)
        low = next((a for a in attrs(client, cid) if a["data_type"] == "number" and a["better"] == "lower"), None)
        if low:
            break
    else:
        pytest.skip("no lower-is-better attr")
    h, _ = api.seller()
    a = make_product(api, h, client, slug=slug, values=[{"key": low["key"], "value_num": 300}])
    b_ = make_product(api, h, client, slug=slug, values=[{"key": low["key"], "value_num": 200}])
    row = next(r for r in all_rows(compare(client, [a["id"], b_["id"]]).json()) if r["key"] == low["key"])
    assert [c["is_best"] for c in row["cells"]] == [False, True]


def test_compare_tie_gives_no_spec_badge(api, client):
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    if not num["badge_label"]:
        pytest.skip("attr has no badge_label")
    h, _ = api.seller()
    a = make_product(api, h, client, values=[{"key": num["key"], "value_num": 20}])
    b_ = make_product(api, h, client, values=[{"key": num["key"], "value_num": 20}])
    body = compare(client, [a["id"], b_["id"]]).json()
    assert all(num["badge_label"] not in i["badges"] for i in body["items"])


def test_compare_diff_only_hides_identical_rows(api, client):
    cid = cat_id(client, "electronics")
    req = required_values(client, cid)
    h, _ = api.seller()
    a = make_product(api, h, client, values=req)
    b_ = make_product(api, h, client, values=req)
    on = compare(client, [a["id"], b_["id"]], diff_only="true").json()
    off = compare(client, [a["id"], b_["id"]], diff_only="false").json()
    assert all(r["differs"] for r in all_rows(on))
    same_keys = {r["key"] for r in all_rows(off) if not r["differs"]}
    assert {v["key"] for v in req} <= same_keys
    assert not same_keys & {r["key"] for r in all_rows(on)}


def test_compare_diff_only_default_true(api, client):
    cid = cat_id(client, "electronics")
    req = required_values(client, cid)
    h, _ = api.seller()
    a = make_product(api, h, client, values=req)
    b_ = make_product(api, h, client, values=req)
    assert all(r["differs"] for r in all_rows(compare(client, [a["id"], b_["id"]]).json()))


def test_compare_missing_value_is_null_display(api, client):
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    h, _ = api.seller()
    a = make_product(api, h, client, values=[{"key": num["key"], "value_num": 10}])
    b_ = make_product(api, h, client, values=[])
    row = next(r for r in all_rows(compare(client, [a["id"], b_["id"]]).json()) if r["key"] == num["key"])
    assert row["cells"][1]["display"] is None and row["cells"][1]["is_best"] is False


def test_compare_different_categories(api, client):
    h, _ = api.seller()
    a = make_product(api, h, client, slug="electronics", values=required_values(client, cat_id(client, "electronics")))
    b_ = make_product(api, h, client, slug="kitchen", values=required_values(client, cat_id(client, "kitchen")))
    body = compare(client, [a["id"], b_["id"]]).json()
    assert body["same_category"] is False and body["groups"] == []
    spec_labels = {x["badge_label"] for s in ("electronics", "kitchen") for x in attrs(client, cat_id(client, s)) if x["badge_label"]}
    assert not any(set(i["badges"]) & spec_labels for i in body["items"])
    for i in body["items"]:  # ราคา/รีวิว/ค่าส่ง ยังมี
        assert "price" in i and "rating" in i and i["shipping"] is not None


def test_compare_cheapest_including_shipping(api, client):
    """A ถูกกว่าตัวสินค้า แต่ค่าส่งแพง → B ได้ป้าย ถูกที่สุด (รวมค่าส่ง)"""
    ha, _ = api.seller()
    hb, _ = api.seller()
    client.put("/api/shops/me/shipping", headers=ha, json={"flat_rate": 200, "free_over": None, "days_min": 2, "days_max": 4, "region_rates": []})
    client.put("/api/shops/me/shipping", headers=hb, json={"flat_rate": 0, "free_over": None, "days_min": 2, "days_max": 4, "region_rates": []})
    a = make_product(api, ha, client, price=300)
    b_ = make_product(api, hb, client, price=400)
    body = compare(client, [a["id"], b_["id"]]).json()
    assert body["items"][0]["total"] == 500 and body["items"][1]["total"] == 400
    assert "ถูกที่สุด (รวมค่าส่ง)" in body["items"][1]["badges"]
    assert "ถูกที่สุด (รวมค่าส่ง)" not in body["items"][0]["badges"]


def test_compare_shipping_by_province(api, client):
    h, _ = api.seller()
    region = _region_of(client, "เชียงใหม่")
    client.put("/api/shops/me/shipping", headers=h, json={"flat_rate": 40, "free_over": None, "days_min": 2, "days_max": 4,
                                                          "region_rates": [{"region": region, "rate": 120, "days_min": 4, "days_max": 7}]})
    p = make_product(api, h, client, price=300)
    cm = compare(client, [p["id"]], province="เชียงใหม่").json()
    assert cm["province"] == "เชียงใหม่" and cm["region"] == region
    sh = cm["items"][0]["shipping"]
    assert (sh["fee"], sh["days_min"], sh["days_max"]) == (120, 4, 7)
    flat = compare(client, [p["id"]]).json()
    assert flat["items"][0]["shipping"]["fee"] == 40


def test_compare_free_over_threshold(api, client):
    h, _ = api.seller()
    p = make_product(api, h, client, price=600)  # ค่าเริ่มต้น free_over 500
    assert compare(client, [p["id"]]).json()["items"][0]["shipping"]["fee"] == 0


def test_compare_review_badge_needs_reviews(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, price=100, stock=5)
    b_ = make_product(api, h2, client, price=100, stock=5)
    body = compare(client, [a["id"], b_["id"]]).json()
    assert all("รีวิวดีที่สุด" not in i["badges"] for i in body["items"])
    reviewed(api, client, h1, a["id"], 3)
    reviewed(api, client, h2, b_["id"], 5)
    body = compare(client, [a["id"], b_["id"]]).json()
    assert "รีวิวดีที่สุด" in body["items"][1]["badges"] and "รีวิวดีที่สุด" not in body["items"][0]["badges"]


def test_compare_summary_numbers_match_table(client, trio):
    items, _ = trio
    body = compare(client, [p["id"] for _, _, p in items]).json()
    s = body["summary"]
    if s is None:
        return
    assert isinstance(s, str) and "\n" not in s.strip()
    allowed = set()
    vals = []
    for it in body["items"]:
        vals += [it["price"], it["total"], it["shipping"]["fee"], it["shipping"]["days_min"], it["shipping"]["days_max"]]
    for row in all_rows(compare(client, [p["id"] for _, _, p in items], diff_only="false").json()):
        for c in row["cells"]:
            vals += [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", c["display"] or "")]
    for x in vals:
        allowed.add(float(x))
    for x in vals:
        for y in vals:
            allowed.add(abs(float(x) - float(y)))
    for n in re.findall(r"\d[\d,]*\.?\d*", s):
        num = float(n.replace(",", ""))
        assert num in allowed or num <= 4, f"ตัวเลข {n} ในสรุปไม่ตรงกับตาราง: {s}"


def test_compare_summary_cached_and_refreshed(client, api, trio):
    items, _ = trio
    ids = [p["id"] for _, _, p in items]
    s1 = compare(client, ids).json()["summary"]
    assert compare(client, ids).json()["summary"] == s1
    h, _, p = items[0]
    api.set_price(h, p["id"], 500)  # fingerprint เปลี่ยน → สรุปต้องคำนวณใหม่จากตัวเลขปัจจุบัน
    body = compare(client, ids).json()
    assert body["items"][0]["price"] == 500
    if body["summary"] and s1:
        assert "1,000" not in body["summary"] or body["summary"] != s1


# ================================================================== same model / similar

def test_same_model_by_barcode_other_shops_only(api, client):
    h1, s1 = api.seller()
    h2, s2 = api.seller()
    a = make_product(api, h1, client, barcode="8850000000017", price=500)
    own = make_product(api, h1, client, barcode="8850000000017", price=450)
    b_ = make_product(api, h2, client, barcode="8850000000017", price=480)
    r = client.get(f"/api/products/{a['id']}/same-model").json()
    assert [x["product_id"] for x in r] == [b_["id"]]
    x = r[0]
    assert x["match"] == "barcode" and x["shop_id"] == s2["id"]
    assert x["total"] == x["price"] + x["shipping_fee"]
    assert own["id"] not in [y["product_id"] for y in r]


def test_same_model_brand_model_case_insensitive(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, brand="Sony", model_code="WH-1000XM5")
    b_ = make_product(api, h2, client, brand=" sony ", model_code="wh-1000xm5")
    r = client.get(f"/api/products/{a['id']}/same-model").json()
    assert [x["product_id"] for x in r] == [b_["id"]] and r[0]["match"] == "brand_model"


def test_same_model_requires_both_brand_and_model(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, brand="Sony", model_code="A1")
    make_product(api, h2, client, brand="Sony", model_code="A2")
    make_product(api, h2, client, brand="Panasonic", model_code="A1")
    make_product(api, h2, client, brand="Sony")
    assert client.get(f"/api/products/{a['id']}/same-model").json() == []


def test_same_model_empty_without_codes(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, name="หูฟัง")
    make_product(api, h2, client, name="หูฟัง")
    assert client.get(f"/api/products/{a['id']}/same-model").json() == []


def test_same_model_excludes_inactive(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, barcode="111")
    b_ = make_product(api, h2, client, barcode="111")
    client.delete(f"/api/products/{b_['id']}", headers=h2)
    assert client.get(f"/api/products/{a['id']}/same-model").json() == []


def test_similar_same_category_closest_price(api, client):
    h, _ = api.seller()
    base = make_product(api, h, client, price=1000)
    near = make_product(api, h, client, price=1050)
    mid = make_product(api, h, client, price=1300)
    far = make_product(api, h, client, price=3000)
    make_product(api, h, client, slug="kitchen", price=1000)
    r = client.get(f"/api/products/{base['id']}/similar?limit=2").json()
    assert [x["id"] for x in r] == [near["id"], mid["id"]]
    all_ = [x["id"] for x in client.get(f"/api/products/{base['id']}/similar?limit=10").json()]
    assert base["id"] not in all_ and far["id"] in all_ and len(all_) == 3


# ================================================================== compare list

def test_compare_list_account(api, client):
    h, _ = api.seller()
    ps = [make_product(api, h, client)["id"] for _ in range(3)]
    hb = api.user()
    assert client.get("/api/account/compare-list").status_code == 401
    assert client.get("/api/account/compare-list", headers=hb).json() == {"ids": []}
    r = client.put("/api/account/compare-list", json={"ids": ps + [999999]}, headers=hb)
    assert r.status_code == 200 and r.json()["ids"] == ps
    assert client.get("/api/account/compare-list", headers=hb).json()["ids"] == ps
    assert client.put("/api/account/compare-list", json={"ids": [1, 2, 3, 4, 5]}, headers=hb).status_code == 422


def test_compare_list_per_user(api, client):
    h, _ = api.seller()
    p = make_product(api, h, client)
    u1, u2 = api.user(), api.user()
    client.put("/api/account/compare-list", json={"ids": [p["id"]]}, headers=u1)
    assert client.get("/api/account/compare-list", headers=u2).json()["ids"] == []


# ================================================================== ranking

def test_spec_complete_ranking_boost_default_sort(api, client):
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    req = required_values(client, cid)
    complete = make_product(api, h, client, name="ครบ", values=req)
    others = [make_product(api, h, client, name=f"ไม่ครบ{i}") for i in range(5)]
    ids = [p["id"] for p in client.get("/api/products").json()]
    # latest: ใหม่สุดก่อน → ไม่ครบ4..0 แล้วครบ (ตำแหน่ง 5) → ขยับขึ้น 3 = ตำแหน่ง 2
    assert ids.index(complete["id"]) == 2, ids
    ids_cat = [p["id"] for p in client.get(f"/api/products?category_id={cid}").json()]
    assert ids_cat.index(complete["id"]) == 2


def test_no_boost_on_explicit_sort(api, client):
    h, _ = api.seller()
    req = required_values(client, cat_id(client, "electronics"))
    complete = make_product(api, h, client, price=900, values=req)
    cheap = [make_product(api, h, client, price=100 + i)["id"] for i in range(4)]
    ids = [p["id"] for p in client.get("/api/products?sort=price_asc").json()]
    assert ids == cheap + [complete["id"]]


def test_first_shipping_save_keeps_free_over_null(api, client):
    """บั๊กที่เคยเจอ: บันทึกค่าส่งครั้งแรก (ยังไม่เคย GET) ส่ง free_over=null แล้วถูกเก็บเป็น 500"""
    h, _ = api.seller()
    body = {"flat_rate": 60, "free_over": None, "days_min": 1, "days_max": 2, "region_rates": []}
    r = client.put("/api/shops/me/shipping", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["free_over"] is None
    assert client.get("/api/shops/me/shipping", headers=h).json()["free_over"] is None
    # มีผลจริงตอนคิดค่าส่ง: ซื้อเกิน 500 ก็ยังเสียค่าส่ง
    p = api.product(h, price=900, stock=5)
    assert compare(client, [p["id"]]).json()["items"][0]["shipping"]["fee"] == 60
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    o = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT, headers=hb).json()[0]
    assert o["shipping_fee"] == 60


def test_shipping_put_partial_body_keeps_free_over_null(api, client):
    h, _ = api.seller()
    client.put("/api/shops/me/shipping", json={"flat_rate": 60, "free_over": None, "days_min": 1, "days_max": 2, "region_rates": []}, headers=h)
    r = client.put("/api/shops/me/shipping", json={"flat_rate": 70, "free_over": None, "days_min": 1, "days_max": 2, "region_rates": []}, headers=h)
    assert r.json()["free_over"] is None and r.json()["flat_rate"] == 70


def test_shipping_validation(api, client):
    h, _ = api.seller()
    bad = [
        {"flat_rate": -1, "free_over": None, "days_min": 1, "days_max": 2, "region_rates": []},
        {"flat_rate": 40, "free_over": None, "days_min": 5, "days_max": 2, "region_rates": []},
        {"flat_rate": 40, "free_over": None, "days_min": 1, "days_max": 2,
         "region_rates": [{"region": "ดาวอังคาร", "rate": 10, "days_min": 1, "days_max": 2}]},
    ]
    for b in bad:
        assert client.put("/api/shops/me/shipping", json=b, headers=h).status_code in (400, 422), b


def test_cart_shipping_quote_matches_checkout(api, client):
    hs, _ = api.seller()
    region = _region_of(client, "เชียงใหม่")
    client.put("/api/shops/me/shipping", headers=hs, json={"flat_rate": 40, "free_over": 500, "days_min": 2, "days_max": 4,
                                                           "region_rates": [{"region": region, "rate": 75, "days_min": 3, "days_max": 6}]})
    p1 = api.product(hs, price=100, stock=5)
    hs2, _ = api.seller()
    p2 = api.product(hs2, price=700, stock=5)
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, p1["id"], h=hb)
    api.add_to_cart(token, p2["id"], h=hb)
    q = client.get(f"/api/cart/{token}/shipping-quote?province=เชียงใหม่", headers=hb)
    assert q.status_code == 200, q.text
    orders = client.post(f"/api/orders/checkout?token={token}", json=dict(CHECKOUT, province="เชียงใหม่"), headers=hb).json()
    qj = q.json()
    assert qj["province"] == "เชียงใหม่"
    assert qj["grand_total"] == sum(o["total"] for o in orders)
    assert qj["shipping_total"] == sum(o["shipping_fee"] for o in orders)
    fees = {sq["shop_id"]: sq["fee"] for sq in qj["shops"]}
    assert fees[p1["shop_id"]] == 75 and fees[p2["shop_id"]] == 0  # 700 ≥ free_over 500


def test_compare_uses_account_province_when_logged_in(api, client):
    hs, _ = api.seller()
    region = _region_of(client, "เชียงใหม่")
    client.put("/api/shops/me/shipping", headers=hs, json={"flat_rate": 40, "free_over": None, "days_min": 2, "days_max": 4,
                                                           "region_rates": [{"region": region, "rate": 99, "days_min": 3, "days_max": 5}]})
    p = make_product(api, hs, client, price=300)
    hb = api.user()
    client.put("/api/account/province", json={"province": "เชียงใหม่"}, headers=hb)
    r = client.get(f"/api/compare?ids={p['id']}", headers=hb).json()
    assert r["province"] == "เชียงใหม่" and r["items"][0]["shipping"]["fee"] == 99
    # ส่ง province มาเองชนะค่าของบัญชี
    r = client.get(f"/api/compare?ids={p['id']}&province=กรุงเทพมหานคร", headers=hb).json()
    assert r["items"][0]["shipping"]["fee"] == 40


def test_compare_enum_rank_by_option_order(api, client):
    for slug in SLUGS:
        cid = cat_id(client, slug)
        en = next((a for a in attrs(client, cid)
                   if a["data_type"] == "enum" and a["better"] in ("higher", "lower") and len(a["options"]) >= 2), None)
        if en:
            break
    else:
        pytest.skip("no ranked enum attr")
    h, _ = api.seller()
    lo = make_product(api, h, client, slug=slug, values=[{"key": en["key"], "value_text": en["options"][0]}])
    hi = make_product(api, h, client, slug=slug, values=[{"key": en["key"], "value_text": en["options"][-1]}])
    row = next(r for r in all_rows(compare(client, [lo["id"], hi["id"]]).json()) if r["key"] == en["key"])
    expect = [False, True] if en["better"] == "higher" else [True, False]
    assert [c["is_best"] for c in row["cells"]] == expect


def test_compare_summary_row_cached_per_set_and_province(api, client, trio):
    from sqlmodel import Session, select
    from app import models
    from app.database import engine
    items, _ = trio
    ids = [p["id"] for _, _, p in items]
    compare(client, ids)
    compare(client, list(reversed(ids)))  # ลำดับต่างแต่ชุดเดียวกัน → แถวเดียว
    compare(client, ids, province="เชียงใหม่")
    with Session(engine) as s:
        n = len(s.exec(select(models.CompareSummary)).all())
    assert n == 2


# ================================================================== follow-ups ที่ตกลงกันใน team-log

def test_features_endpoint(client):
    r = client.get("/api/features")
    assert r.status_code == 200, r.text
    f = r.json()
    assert isinstance(f["spec_suggest"], bool) and isinstance(f["chat"], bool)
    assert isinstance(f["chat_rollout_percent"], (int, float)) and 0 <= f["chat_rollout_percent"] <= 100


def test_features_spec_suggest_follows_llm_provider(client, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none", raising=False)
    assert client.get("/api/features").json()["spec_suggest"] is False
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake", raising=False)
    assert client.get("/api/features").json()["spec_suggest"] is True


def test_compare_free_reason(api, client):
    h, _ = api.seller()
    over = make_product(api, h, client, price=600)                       # ≥ free_over 500
    item_free = make_product(api, h, client, price=100, free_shipping=True)
    paid = make_product(api, h, client, price=100)
    items = compare(client, [over["id"], item_free["id"], paid["id"]]).json()["items"]
    s = [i["shipping"] for i in items]
    assert s[0]["fee"] == 0 and s[0]["free_reason"] == "threshold" and s[0]["free_over"] == 500
    assert s[1]["fee"] == 0 and s[1]["free_reason"] == "item"
    assert s[2]["fee"] == 40 and s[2]["free_reason"] is None



def test_different_categories_no_cheapest_badge_fixed_summary(api, client):
    ha, _ = api.seller()
    hb, _ = api.seller()
    a = make_product(api, ha, client, slug="electronics", price=100)
    b_ = make_product(api, hb, client, slug="kitchen", price=900)
    body = compare(client, [a["id"], b_["id"]]).json()
    assert all("ถูกที่สุด (รวมค่าส่ง)" not in i["badges"] for i in body["items"])
    assert body["summary"] == "สินค้าต่างประเภทกัน เทียบได้แค่ราคา ค่าส่ง และรีวิว"


def test_different_categories_review_badge_still_applies(api, client):
    ha, _ = api.seller()
    hb, _ = api.seller()
    a = make_product(api, ha, client, slug="electronics", price=100, stock=5)
    b_ = make_product(api, hb, client, slug="kitchen", price=100, stock=5)
    reviewed(api, client, ha, a["id"], 2)
    reviewed(api, client, hb, b_["id"], 5)
    body = compare(client, [a["id"], b_["id"]]).json()
    assert "รีวิวดีที่สุด" in body["items"][1]["badges"]


def test_same_model_and_quote_carry_free_reason(api, client):
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, barcode="222", price=100)
    make_product(api, h2, client, barcode="222", price=600)
    row = client.get(f"/api/products/{a['id']}/same-model").json()[0]
    assert row["shipping_fee"] == 0 and row["free_reason"] == "threshold" and row["free_over"] == 500
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, a["id"], h=hb)
    sq = client.get(f"/api/cart/{token}/shipping-quote", headers=hb).json()["shops"][0]
    assert sq["fee"] == 40 and sq["free_reason"] is None and sq["free_over"] == 500


def test_html_served_no_cache(client):
    for path in ("/", "/pages/compare.html"):
        assert "no-cache" in client.get(path).headers.get("cache-control", ""), path
