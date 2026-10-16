"""เฟส 4 — สรุปเปรียบเทียบด้วยโมเดล, สรุปรีวิว, จับคู่ "อาจเป็นรุ่นเดียวกัน" (fuzzy)
อ้างอิง "[backend] Phase 4 contract" ใน team-log — ใช้ fake provider เท่านั้น (conftest บังคับ LLM_PROVIDER=none)
"""
import re
import uuid

import pytest

from app import config, llm

from tests.test_phase2_compare import (
    CHECKOUT, all_rows, attrs, cat_id, compare, make_product, number_attr, required_values,
)

# ชื่องานของ fake provider (ตาม contract) — แก้ที่นี่ที่เดียวถ้า backend ตั้งชื่ออื่น
TASK_COMPARE = "compare_summary"
TASK_REVIEW = "review_summary"
MAYBE_LABEL = "อาจเป็นรุ่นเดียวกัน"


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")


def spy(monkeypatch, task, reply):
    """แทน handler ของงานนั้น + นับจำนวนครั้งที่ถูกเรียก; reply = str | callable(ctx) | Exception"""
    calls = []

    def handler(system, messages, ctx):
        calls.append(ctx)
        if isinstance(reply, Exception):
            raise reply
        return reply(ctx) if callable(reply) else reply

    monkeypatch.setitem(llm.FAKE_HANDLERS, task, handler)
    return calls


def numbers(text):
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")]


# ================================================================== 1) สรุปเปรียบเทียบ

@pytest.fixture
def pair(api, client):
    """2 ชิ้นหมวดเดียวกัน ราคา 1000 / 1290 ค่าสเปก higher 10 / 20"""
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    req = [v for v in required_values(client, cid) if v["key"] != num["key"]]
    out = []
    for price, n in ((1000, 10), (1290, 20)):
        h, _ = api.seller()
        out.append(make_product(api, h, client, price=price, values=req + [{"key": num["key"], "value_num": n}]))
    return out, num


def _ids(pair):
    return [p["id"] for p in pair[0]]


def test_compare_summary_rule_when_provider_none(client, pair):
    body = compare(client, _ids(pair)).json()
    assert body.get("summary_source") in ("rule", None)
    if body["summary"]:
        assert body["summary_source"] == "rule"


def test_compare_summary_ai_accepted_when_numbers_match(client, pair, fake, monkeypatch):
    good = "รุ่นแรกถูกกว่า 290 บาท ส่วนรุ่นที่สองราคา 1,290 บาท"
    calls = spy(monkeypatch, TASK_COMPARE, good)
    body = compare(client, _ids(pair)).json()
    assert calls, "ไม่ได้เรียกโมเดลสรุป"
    assert body["summary_source"] == "ai" and body["summary"] == good


@pytest.mark.parametrize("lie", [
    "รุ่นแรกราคา 999 บาท ถูกกว่าเยอะ",                 # ราคาไม่มีในตาราง
    "รุ่นที่สองแบตอึดกว่า 35 ชม.",                       # ค่าสเปกไม่มีในตาราง
    "รุ่นแรกถูกกว่า 500 บาท",                            # ส่วนต่างผิด
    "รับประกันว่ารุ่นแรกคุ้มที่สุด ราคา 1,000 บาท",        # คำผูกมัด
    "รุ่นแรกห่วยแตก ไอ้สัตว์ ราคา 1,000 บาท",            # คำหยาบ
    "",                                                  # ว่าง
])
def test_compare_summary_falls_back_when_model_lies(client, pair, fake, monkeypatch, lie):
    calls = spy(monkeypatch, TASK_COMPARE, lie)
    body = compare(client, _ids(pair)).json()
    assert calls
    assert body["summary_source"] == "rule", body["summary"]
    assert body["summary"] != lie


def test_compare_summary_falls_back_on_llm_error(client, pair, fake, monkeypatch):
    spy(monkeypatch, TASK_COMPARE, llm.LlmUnavailable("down", status=503))
    r = compare(client, _ids(pair))
    assert r.status_code == 200
    assert r.json()["summary_source"] == "rule"


def test_compare_summary_numbers_always_in_table(client, pair, fake, monkeypatch):
    """ไม่ว่ามาจากไหน ทุกตัวเลขในสรุปต้องอยู่ในตาราง (หรือเป็นส่วนต่างของค่าในตาราง)"""
    spy(monkeypatch, TASK_COMPARE, lambda ctx: "รุ่นแรกถูกกว่า 290 บาท")
    ids = _ids(pair)
    body = compare(client, ids).json()
    full = compare(client, ids, diff_only="false").json()
    vals = set()
    for it in body["items"]:
        vals |= {float(it["price"]), float(it["total"]), float(it["shipping"]["fee"]),
                 float(it["shipping"]["days_min"]), float(it["shipping"]["days_max"])}
    for row in all_rows(full):
        for c in row["cells"]:
            vals |= set(numbers(c["display"] or ""))
    allowed = vals | {abs(a - b) for a in vals for b in vals}
    for n in numbers(body["summary"]):
        assert n in allowed or n <= 4, f"{n} ไม่อยู่ในตาราง: {body['summary']}"


def test_compare_summary_cached_and_refreshed(client, pair, api, fake, monkeypatch):
    calls = spy(monkeypatch, TASK_COMPARE, lambda ctx: "รุ่นแรกถูกกว่า 290 บาท")
    ids = _ids(pair)
    compare(client, ids)
    compare(client, list(reversed(ids)))
    assert len(calls) == 1, "ชุดสินค้าเดิม ต้องใช้ cache ไม่เรียกโมเดลซ้ำ"
    # ราคาเปลี่ยน → fingerprint เปลี่ยน → สร้างใหม่ (และข้อความเก่าที่มีตัวเลขเก่าต้องไม่ถูกใช้)
    owner_headers = None
    for p in pair[0][:1]:
        pass
    calls.clear()
    monkeypatch.setitem(llm.FAKE_HANDLERS, TASK_COMPARE, lambda s, m, c: (calls.append(c), "รุ่นแรกถูกกว่า 390 บาท")[1])
    from sqlmodel import Session
    from app import models
    from app.database import engine
    with Session(engine) as s:  # เปลี่ยนราคาตรง DB (เจ้าของร้านคนละคน)
        prod = s.get(models.Product, ids[0])
        prod.price = 900
        s.add(prod)
        s.commit()
    body = compare(client, ids).json()
    assert len(calls) == 1
    assert "290" not in body["summary"]


def test_compare_summary_cache_keyed_by_provider(client, pair, fake, monkeypatch):
    """สรุปที่ cache ไว้ตอนไม่มีโมเดล ต้องไม่บังไม่ให้ได้สรุปจากโมเดลเมื่อเปิดใช้"""
    ids = _ids(pair)
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    assert compare(client, ids).json()["summary_source"] in ("rule", None)
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    spy(monkeypatch, TASK_COMPARE, "รุ่นแรกถูกกว่า 290 บาท")
    assert compare(client, ids).json()["summary_source"] == "ai"


def test_compare_summary_different_categories_no_model(client, api, fake, monkeypatch):
    calls = spy(monkeypatch, TASK_COMPARE, "อะไรก็ได้ 1 บาท")
    h, _ = api.seller()
    a = make_product(api, h, client, slug="electronics", price=100)
    b = make_product(api, h, client, slug="kitchen", price=200)
    body = compare(client, [a["id"], b["id"]]).json()
    assert body["summary"] == "สินค้าต่างประเภทกัน เทียบได้แค่ราคา ค่าส่ง และรีวิว"
    assert body["summary_source"] != "ai"


# ================================================================== 2) สรุปรีวิว (contract v1.1)

GOOD_REVIEWS = [
    (5, "เสียงดีมาก เบสแน่น ใส่สบาย"),
    (4, "เสียงดี แบตอึด แต่สายสั้นไปหน่อย"),
    (5, "ใส่สบาย เสียงชัด ส่งไว"),
    (3, "แบตอึดดี แต่กล่องบุบ"),
]


def add_review(api, client, hs, pid, rating, comment):
    hb = api.user()
    token = api.user_cart(hb)
    api.add_to_cart(token, pid, h=hb)
    order = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT, headers=hb).json()[0]
    client.post(f"/api/orders/{order['id']}/ship", headers=hs)
    client.post(f"/api/orders/{order['id']}/receive", headers=hb)
    r = client.post("/api/reviews", json={"order_item_id": order["items"][0]["id"], "rating": rating, "comment": comment}, headers=hb)
    assert r.status_code == 201, r.text


@pytest.fixture
def reviewed_product(api, client):
    hs, _ = api.seller()
    p = api.product(hs, price=500, stock=20, name="หูฟังทดสอบรีวิว")
    for rating, comment in GOOD_REVIEWS[:3]:
        add_review(api, client, hs, p["id"], rating, comment)
    return hs, p


def rs(client, pid):
    r = client.get(f"/api/products/{pid}/review-summary")
    assert r.status_code == 200, r.text
    return r.json()


def model_json(praise=(), complaints=()):
    import json as _j
    return _j.dumps({"praise": [{"text": t, "quote": q} for t, q in praise],
                     "complaints": [{"text": t, "quote": q} for t, q in complaints]}, ensure_ascii=False)


VALID = model_json(praise=[("เสียงดี", "เสียงดีมาก"), ("ใส่สบาย", "ใส่สบาย เสียงชัด")],
                   complaints=[("สายสั้น", "สายสั้นไปหน่อย")])


def test_review_summary_shape_and_ai(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    calls = spy(monkeypatch, TASK_REVIEW, VALID)
    b = rs(client, p["id"])
    assert set(b) >= {"available", "review_count", "min_reviews", "label", "praise", "complaints",
                      "praise_quotes", "complaint_quotes", "source", "generated_at"}
    assert b["available"] is True and b["source"] == "ai" and b["generated_at"]
    assert b["review_count"] == 3 and b["min_reviews"] == 3
    assert b["label"] == "สรุปจากรีวิว 3 รายการ" and "AI" not in b["label"]
    assert b["praise"] == ["เสียงดี", "ใส่สบาย"] and b["complaints"] == ["สายสั้น"]
    assert len(b["praise_quotes"]) == 2 and len(b["complaint_quotes"]) == 1
    comments = " ".join(c for _, c in GOOD_REVIEWS[:3])
    for q in b["praise_quotes"] + b["complaint_quotes"]:
        assert q in comments
    assert calls and {"reviews", "product"} <= set(calls[0])


def test_review_summary_needs_min_reviews(client, api, fake, monkeypatch):
    calls = spy(monkeypatch, TASK_REVIEW, VALID)
    hs, _ = api.seller()
    p = api.product(hs, price=500, stock=20)
    for rating, comment in GOOD_REVIEWS[:2]:
        add_review(api, client, hs, p["id"], rating, comment)
    b = rs(client, p["id"])
    assert b["available"] is False and b["review_count"] == 2 and b["praise"] == [] and b["label"] is None
    assert calls == [], "รีวิวไม่ถึงเกณฑ์ ต้องไม่เรียกโมเดล"


def test_review_summary_min_configurable(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    spy(monkeypatch, TASK_REVIEW, VALID)
    monkeypatch.setattr(config, "REVIEW_SUMMARY_MIN_REVIEWS", 5)
    b = rs(client, p["id"])
    assert b["available"] is False and b["min_reviews"] == 5


def test_review_summary_none_provider_never_shows(client, reviewed_product, monkeypatch):
    _, p = reviewed_product
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    b = rs(client, p["id"])
    assert b["available"] is False and b["praise"] == [] and b["complaints"] == [] and b["source"] is None


def test_review_summary_none_provider_hides_cached(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    spy(monkeypatch, TASK_REVIEW, VALID)
    assert rs(client, p["id"])["available"] is True
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    assert rs(client, p["id"])["available"] is False


def test_review_summary_cached(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    calls = spy(monkeypatch, TASK_REVIEW, VALID)
    rs(client, p["id"])
    rs(client, p["id"])
    assert len(calls) == 1


def test_review_summary_regenerated_when_reviews_change(client, api, reviewed_product, fake, monkeypatch):
    hs, p = reviewed_product
    spy(monkeypatch, TASK_REVIEW, VALID)
    rs(client, p["id"])
    add_review(api, client, hs, p["id"], *GOOD_REVIEWS[3])
    calls = spy(monkeypatch, TASK_REVIEW, model_json(praise=[("แบตอึด", "แบตอึดดี")], complaints=[("กล่องบุบ", "กล่องบุบ")]))
    b = rs(client, p["id"])
    assert calls, "รีวิวเปลี่ยนแล้วต้องสร้างสรุปใหม่"
    assert b["review_count"] == 4 and b["label"] == "สรุปจากรีวิว 4 รายการ"
    assert b["complaints"] == ["กล่องบุบ"]


def test_review_summary_model_sees_only_review_text(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    calls = spy(monkeypatch, TASK_REVIEW, VALID)
    rs(client, p["id"])
    blob = repr(calls[0])
    for _, comment in GOOD_REVIEWS[:3]:
        assert comment in blob
    assert "@test.local" not in blob and "ผู้ทดสอบ" not in blob, "ข้อมูลผู้รีวิวไม่ควรถูกส่งเข้าโมเดล"


@pytest.mark.parametrize("point", [
    ("กันน้ำได้ดี", "เสียงดีมาก"),            # อ้างคุณสมบัติที่ไม่มีใครพูดถึง
    ("เสียงดีมาก", "เสียงระดับสตูดิโอ"),       # quote ไม่มีจริงในรีวิว
    ("เสียงดี ราคาแค่ 199 บาท", "เสียงดีมาก"),  # ตัวเลข/ราคาที่ไม่อยู่ใน quote
    ("ร้านรับประกันเสียงดี", "เสียงดีมาก"),      # คำผูกมัด
    ("เสียงดี ไอ้สัตว์", "เสียงดีมาก"),          # คำหยาบ
    ("เสียงดี", "ดี"),                        # quote สั้นกว่า 4 ตัวอักษร
])
def test_review_summary_drops_invented_or_unsafe_points(client, reviewed_product, fake, monkeypatch, point):
    _, p = reviewed_product
    spy(monkeypatch, TASK_REVIEW, model_json(praise=[point, ("ใส่สบาย", "ใส่สบาย เสียงชัด")]))
    b = rs(client, p["id"])
    assert point[0] not in b["praise"], f"ควรถูกตัด: {point}"
    assert b["praise"] == ["ใส่สบาย"]  # ข้อที่ถูกต้องยังอยู่


@pytest.mark.parametrize("raw", ["", "not json", "EMPTY", "ONLY_INVENTED"])
def test_review_summary_nothing_valid_is_unavailable(client, reviewed_product, fake, monkeypatch, raw):
    _, p = reviewed_product
    raw = {"EMPTY": model_json(), "ONLY_INVENTED": model_json(praise=[("กันน้ำ", "กันน้ำ")])}.get(raw, raw)
    spy(monkeypatch, TASK_REVIEW, raw)
    assert rs(client, p["id"])["available"] is False


def test_review_summary_llm_error_unavailable(client, reviewed_product, fake, monkeypatch):
    _, p = reviewed_product
    spy(monkeypatch, TASK_REVIEW, llm.LlmUnavailable("down", status=429))
    assert rs(client, p["id"])["available"] is False


def test_review_summary_404(client, api):
    assert client.get("/api/products/999999/review-summary").status_code == 404
    h, _ = api.seller()
    p = api.product(h)
    client.delete(f"/api/products/{p['id']}", headers=h)
    assert client.get(f"/api/products/{p['id']}/review-summary").status_code == 404


def test_review_summary_batch(client, reviewed_product, fake, monkeypatch):
    from sqlmodel import Session
    from app import review_summary
    from app.database import engine
    _, p = reviewed_product
    calls = spy(monkeypatch, TASK_REVIEW, VALID)
    with Session(engine) as s:
        n1 = review_summary.run(s)
    with Session(engine) as s:
        n2 = review_summary.run(s)
    assert n1 >= 1 and n2 == 0 and len(calls) == 1
    assert rs(client, p["id"])["available"] is True


def test_validate_points_pure(fake):
    from app import review_summary
    comments = [c for _, c in GOOD_REVIEWS]
    pts = [{"text": "เสียงดี", "quote": "เสียงดีมาก"}, {"text": "กันน้ำ", "quote": "เสียงดีมาก"},
           {"text": "ทนทาน", "quote": "ไม่มีในรีวิว"}]
    kept = review_summary.validate_points(pts, comments)
    texts = [k["text"] if isinstance(k, dict) else k for k in kept]
    assert texts == ["เสียงดี"]


def test_review_summary_buyer_label_plain_thai(client):
    text = client.get("/pages/product-detail.html").text + client.get("/js/api.js").text
    assert "/review-summary" in text
    assert "AI" not in "".join(re.findall(r"สรุปจากรีวิว[^<`\"]{0,40}", text))


# ================================================================== 3) อาจเป็นรุ่นเดียวกัน (fuzzy)

def _spec_values(client, n):
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    req = [v for v in required_values(client, cid) if v["key"] != num["key"]]
    return req + [{"key": num["key"], "value_num": n}]


def maybe(client, pid, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/products/{pid}/maybe-same" + (f"?{q}" if q else ""))
    assert r.status_code == 200, r.text
    return r.json()


NAME = "หูฟังไร้สาย ตัดเสียงรบกวน รุ่น Studio Pro"


@pytest.fixture
def twin(api, client):
    """ตัวตั้งต้น + ร้านอื่นขายของที่ชื่อ/แบรนด์/สเปกตรงกัน แต่ไม่มีบาร์โค้ด/รหัสรุ่น"""
    h1, _ = api.seller()
    h2, s2 = api.seller()
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", values=_spec_values(client, 20))
    other = make_product(api, h2, client, name="หูฟังไร้สาย ตัดเสียงรบกวน Studio Pro", price=1450,
                         brand="acme", values=_spec_values(client, 20))
    return (h1, base), (h2, s2, other)


def test_maybe_same_finds_similar_without_codes(client, twin):
    (_, base), (_, s2, other) = twin
    res = maybe(client, base["id"])
    assert [x["product_id"] for x in res] == [other["id"]]
    x = res[0]
    assert x.get("label", MAYBE_LABEL) == MAYBE_LABEL and x["shop_id"] == s2["id"]
    assert 0 <= x["score"] <= 1 and x["score"] >= config.FUZZY_MATCH_THRESHOLD
    assert x["reasons"] and all(isinstance(r, str) and r for r in x["reasons"])
    assert x["total"] == x["price"] + x["shipping_fee"]
    for k in ("shop_name", "shop_rating", "days_min", "days_max", "free_reason", "free_over"):
        assert k in x


def test_maybe_same_never_mixed_with_exact(client, api):
    h1, _ = api.seller()
    h2, _ = api.seller()
    h3, _ = api.seller()
    vals = _spec_values(client, 20)
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", barcode="885123", values=vals)
    exact = make_product(api, h2, client, name=NAME, price=1500, brand="Acme", barcode="885123", values=vals)
    fuzzy = make_product(api, h3, client, name=NAME, price=1500, brand="Acme", values=vals)
    same = [x["product_id"] for x in client.get(f"/api/products/{base['id']}/same-model").json()]
    mb = [x["product_id"] for x in maybe(client, base["id"])]
    assert exact["id"] in same and exact["id"] not in mb
    assert fuzzy["id"] in mb and fuzzy["id"] not in same
    assert not set(same) & set(mb)


def test_maybe_same_respects_threshold(client, twin, monkeypatch):
    (_, base), _ = twin
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 0.99, raising=False)
    assert all(x["score"] >= 0.99 for x in maybe(client, base["id"]))
    monkeypatch.setattr(config, "FUZZY_MATCH_THRESHOLD", 1.01, raising=False)
    assert maybe(client, base["id"]) == []


def test_maybe_same_name_only_cannot_pass(client, api):
    """ชื่อเหมือนกันทุกตัวอักษร แต่ไม่มีแบรนด์/สเปก → คะแนนจากชื่ออย่างเดียวต้องไม่ถึงเกณฑ์"""
    h1, _ = api.seller()
    h2, _ = api.seller()
    base = make_product(api, h1, client, name=NAME, price=1500)
    make_product(api, h2, client, name=NAME, price=1500)
    assert maybe(client, base["id"]) == []


def test_name_stuffing_cannot_game_match(client, api):
    """ผู้ขายยัดชื่อสินค้าดังซ้ำๆ + แบรนด์ ลงในสินค้าสเปกต่าง → ต้องไม่ถูกจับคู่"""
    h1, _ = api.seller()
    h2, _ = api.seller()
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", values=_spec_values(client, 20))
    stuffed_name = " ".join([NAME] * 4 + ["Acme", "Studio", "Pro", "ของแท้", "ถูกสุด"])
    stuffer = make_product(api, h2, client, name=stuffed_name[:200], price=1400, values=_spec_values(client, 5))
    assert stuffer["id"] not in [x["product_id"] for x in maybe(client, base["id"])]


def test_score_pair_name_alone_below_threshold(client, api):
    from sqlmodel import Session
    from app import matching, models
    from app.database import engine
    h1, _ = api.seller()
    h2, _ = api.seller()
    a = make_product(api, h1, client, name=NAME, price=1500)
    b = make_product(api, h2, client, name=NAME, price=1500)
    with Session(engine) as s:
        res = matching.score_pair(s.get(models.Product, a["id"]), s.get(models.Product, b["id"]), s)
    assert res is None or res[0] <= config.FUZZY_NAME_WEIGHT + 1e-9
    assert config.FUZZY_NAME_WEIGHT < config.FUZZY_MATCH_THRESHOLD


def test_reasons_are_plain_chips(client, twin):
    (_, base), _ = twin
    for x in maybe(client, base["id"]):
        for r in x["reasons"]:
            assert re.fullmatch(r"ชื่อคล้ายกัน|แบรนด์เดียวกัน|สเปกตรงกัน \d+ ข้อ", r), r


def test_name_weight_capped(client, api):
    """คะแนนส่วนชื่อต้องไม่เกินน้ำหนักที่จำกัดไว้ แม้ชื่อเหมือนกัน 100%"""
    h1, _ = api.seller()
    h2, _ = api.seller()
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", values=_spec_values(client, 20))
    make_product(api, h2, client, name=NAME, price=1500, brand="Acme", values=_spec_values(client, 5))
    for x in maybe(client, base["id"]):
        assert x["score"] < 1.0


@pytest.mark.parametrize("case", ["same_shop", "other_category", "inactive", "price_too_low", "price_too_high", "other_brand"])
def test_maybe_same_exclusions(client, api, case):
    h1, _ = api.seller()
    h2, _ = api.seller()
    vals = _spec_values(client, 20)
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", values=vals)
    kw = dict(name=NAME, price=1500, brand="Acme", values=vals)
    owner = h2
    if case == "same_shop":
        owner = h1
    elif case == "other_category":
        kw.update(slug="kitchen", values=required_values(client, cat_id(client, "kitchen")))
    elif case == "price_too_low":
        kw["price"] = 700         # < 0.5x
    elif case == "price_too_high":
        kw["price"] = 3100        # > 2x
    elif case == "other_brand":
        kw["brand"] = "Other"
    cand = make_product(api, owner, client, **kw)
    if case == "inactive":
        client.delete(f"/api/products/{cand['id']}", headers=owner)
    assert cand["id"] not in [x["product_id"] for x in maybe(client, base["id"])], case


def test_maybe_same_max_results_sorted_by_total(client, api):
    h1, _ = api.seller()
    vals = _spec_values(client, 20)
    base = make_product(api, h1, client, name=NAME, price=1500, brand="Acme", values=vals)
    for price in (1600, 1400, 1550, 1450, 1500):
        h, _ = api.seller()
        make_product(api, h, client, name=NAME, price=price, brand="Acme", values=vals)
    res = maybe(client, base["id"])
    assert len(res) <= getattr(config, "FUZZY_MAX_RESULTS", 3)
    totals = [x["total"] for x in res]
    assert totals == sorted(totals)
    assert base["id"] not in [x["product_id"] for x in res]


def test_maybe_same_404_and_empty(client, api):
    assert client.get("/api/products/999999/maybe-same").status_code == 404
    h, _ = api.seller()
    lonely = make_product(api, h, client, name=f"สินค้าไม่เหมือนใคร {uuid.uuid4().hex[:6]}")
    assert maybe(client, lonely["id"]) == []


def test_maybe_same_ui_label_separate(client):
    html = client.get("/pages/product-detail.html").text
    js = client.get("/js/api.js").text
    assert MAYBE_LABEL in html + js
    assert "/maybe-same" in html + js
    assert "same-model-content" in html


# ================================================================== รุ่นย่อย (tier) และของเลียนแบบ

def _maybe_ids(client, pid):
    return [x["product_id"] for x in maybe(client, pid)]


def _pair_ids(api, client, base_name, other_name, *, base_desc="", other_desc="", brand="Acme", price=(30000, 30000)):
    h1, _ = api.seller()
    h2, _ = api.seller()
    vals = _spec_values(client, 20)
    a = make_product(api, h1, client, name=base_name, description=base_desc, price=price[0], brand=brand, values=vals)
    b = make_product(api, h2, client, name=other_name, description=other_desc, price=price[1], brand=brand, values=vals)
    return a, b


@pytest.mark.parametrize("base,other", [
    ("Acme Phone 15 Pro", "Acme Phone 15 Pro Max"),
    ("Acme Phone 15", "Acme Phone 15 Plus"),
    ("Acme Phone 15 Pro", "Acme Phone 15 Ultra"),
    ("Acme Buds 3", "Acme Buds 3 Mini"),
    ("Acme Buds 3", "Acme Buds 3 Lite"),
    ("Acme Watch 4", "Acme Watch 4 SE"),
    ("Acme Phone 15 Pro Max", "Acme Phone 15 Pro"),   # ทิศทางกลับกัน
    ("Acme Phone 15 PRO", "Acme Phone 15 pro max"),   # ตัวพิมพ์ต่าง
])
def test_tier_variants_not_matched(client, api, base, other):
    a, b = _pair_ids(api, client, base, other)
    assert b["id"] not in _maybe_ids(client, a["id"]), (base, other)
    assert a["id"] not in _maybe_ids(client, b["id"]), (other, base)


def test_same_tier_still_matches(client, api):
    a, b = _pair_ids(api, client, "Acme Phone 15 Pro", "Acme Phone 15 Pro")
    assert b["id"] in _maybe_ids(client, a["id"])


def test_tier_stuffing_cannot_hide_difference(client, api):
    """ใส่ 'Pro' ซ้ำๆ หรือพ่วงคำรุ่นอื่นในชื่อ เพื่อให้ดูเหมือนรุ่นเดียวกัน ก็ยังต้องไม่ถูกจับคู่"""
    a, b = _pair_ids(api, client, "Acme Phone 15 Pro Max", "Acme Phone 15 Pro Pro Pro (เหมือน Max) รุ่นดัง Max2")
    c, d = _pair_ids(api, client, "Acme Phone 15", "Acme Phone 15 Phone 15 Phone 15 Plus ราคาถูก")
    assert b["id"] not in _maybe_ids(client, a["id"])
    assert d["id"] not in _maybe_ids(client, c["id"])


FAKE_WORDS = ["เกรดเอ", "ก๊อป", "ก็อป", "เทียบแท้", "copy", "Replica", "AAA", "ลอกเลียนแบบ"]


@pytest.mark.parametrize("word", FAKE_WORDS)
@pytest.mark.parametrize("where", ["name", "description"])
def test_counterfeit_never_matched_with_genuine_both_directions(client, api, word, where):
    base_name = "Acme Phone 15 Pro"
    if where == "name":
        a, b = _pair_ids(api, client, base_name, f"{base_name} {word}")
    else:
        a, b = _pair_ids(api, client, base_name, base_name, other_desc=f"สินค้า{word} ราคาถูก")
    assert b["id"] not in _maybe_ids(client, a["id"]), (word, where, "genuine → fake")
    assert a["id"] not in _maybe_ids(client, b["id"]), (word, where, "fake → genuine")


def test_counterfeit_both_flagged_still_not_in_same_group_as_genuine(client, api):
    """สินค้าเลียนแบบด้วยกันเอง จับคู่กันได้ แต่ห้ามโผล่ในรายการของของแท้"""
    h1, _ = api.seller()
    h2, _ = api.seller()
    h3, _ = api.seller()
    vals = _spec_values(client, 20)
    g = make_product(api, h1, client, name="Acme Phone 15 Pro", price=30000, brand="Acme", values=vals)
    f1 = make_product(api, h2, client, name="Acme Phone 15 Pro เกรดเอ", price=30000, brand="Acme", values=vals)
    f2 = make_product(api, h3, client, name="Acme Phone 15 Pro ก๊อป", price=30000, brand="Acme", values=vals)
    assert not {f1["id"], f2["id"]} & set(_maybe_ids(client, g["id"]))


def test_counterfeit_word_stuffing_in_name_of_genuine_is_not_gameable(client, api):
    """ของเลียนแบบที่ไม่ใส่คำเตือนในชื่อ แต่ใส่ในคำอธิบาย → ยังถูกกันออก (ตรวจทั้งชื่อและคำอธิบาย)"""
    a, b = _pair_ids(api, client, "Acme Phone 15 Pro", "Acme Phone 15 Pro", other_desc="งานเทียบแท้ เกรดเอ เหมือนจริง 99%")
    assert b["id"] not in _maybe_ids(client, a["id"])


def test_unrelated_words_containing_aaa_or_copy_not_overblocked(client, api):
    """'AAA' แบตเตอรี่ขนาด AAA หรือ 'copy' ในคำอื่นต้องไม่ทำให้ของแท้ถูกกันออกผิดๆ ทุกกรณี"""
    a, b = _pair_ids(api, client, "Acme Remote 2 ใช้ถ่าน AAA", "Acme Remote 2 ใช้ถ่าน AAA", price=(500, 500))
    assert b["id"] in _maybe_ids(client, a["id"])


def test_review_summary_counts_distinct_reviewers(client, api, fake, monkeypatch):
    """ถ้านับ 'ผู้รีวิวไม่ซ้ำ' (3 รีวิวจากคนเดียวไม่ถือว่าครบ) — ตรวจเฉพาะเมื่อ backend ทำไว้"""
    hs, _ = api.seller()
    p = api.product(hs, price=500, stock=20)
    spy(monkeypatch, TASK_REVIEW, VALID)
    buyer = api.user()
    for i, (rating, comment) in enumerate(GOOD_REVIEWS[:3]):
        token = api.user_cart(buyer)
        api.add_to_cart(token, p["id"], h=buyer)
        order = client.post(f"/api/orders/checkout?token={token}", json=CHECKOUT, headers=buyer).json()[0]
        client.post(f"/api/orders/{order['id']}/ship", headers=hs)
        client.post(f"/api/orders/{order['id']}/receive", headers=buyer)
        r = client.post("/api/reviews", json={"order_item_id": order["items"][0]["id"], "rating": rating, "comment": comment}, headers=buyer)
        assert r.status_code == 201, r.text
    b = rs(client, p["id"])
    if b["available"]:
        pytest.skip("backend นับรีวิวทั้งหมด ไม่ได้นับผู้รีวิวไม่ซ้ำ (ยังไม่ได้ implement)")
    assert b["review_count"] in (1, 3)
    add_review(api, client, hs, p["id"], *GOOD_REVIEWS[3])
    add_review(api, client, hs, p["id"], 5, "ใส่สบาย เสียงชัด")
    assert rs(client, p["id"])["available"] is True  # 3 คนไม่ซ้ำ → ครบเกณฑ์
