"""เฟส 4 — ค้นหาตามความหมาย (semantic search) แบบ hybrid ใน GET /api/products?search=
contract v1.1 ข้อ 4: keyword ก่อน (ลำดับเดิม) แล้วต่อด้วย semantic hits; ปิด flag / ไม่มีโมเดล / error → ผลเหมือนเดิมทุกตัว
"""
import math

import pytest
from sqlmodel import Session, select

from app import config, llm, models
from app.database import engine

pytest.importorskip("app.semantic")
from app import semantic  # noqa: E402

from tests.test_phase2_compare import cat_id  # noqa: E402


def ids(client, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/products?{q}")
    assert r.status_code == 200, r.text
    return [p["id"] for p in r.json()]


def backfill():
    with Session(engine) as s:
        return semantic.backfill(s)


@pytest.fixture
def sem_on(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", True)


# ---------- โมเดล embedding ควบคุมได้: ใส่ "ความหมาย" ผ่าน concept → ข้อความที่ไม่มีคำตรงกันก็ใกล้กันได้
CONCEPTS = {
    "audio": ["หูฟัง", "headphone", "earbud", "ฟังเพลง", "ลำโพง"],
    "cook": ["หม้อ", "กระทะ", "ทำอาหาร", "ทอด", "cooking"],
    "sport": ["วิ่ง", "โยคะ", "ออกกำลัง", "fitness"],
}


def concept_embed(self, texts):
    out = []
    for t in texts:
        low = t.lower()
        v = [float(sum(w in low for w in ws)) for ws in CONCEPTS.values()] + [0.01]
        n = math.sqrt(sum(x * x for x in v))
        out.append([x / n for x in v])
    return out


@pytest.fixture
def catalog(api, client):
    h, _ = api.seller()
    el, ki, sp = (cat_id(client, s) for s in ("electronics", "kitchen", "sports"))
    p = {
        "earbuds": api.product(h, name="หูฟังไร้สาย บลูทูธ รุ่นเล็ก", price=890, category_id=el, description="ฟังเพลงเสียงใส"),
        "speaker": api.product(h, name="ลำโพงพกพา", price=1590, category_id=el, description="ฟังเพลงกลางแจ้ง"),
        "pan": api.product(h, name="กระทะเคลือบ 28 ซม.", price=690, category_id=ki, description="ทำอาหารไม่ติด"),
        "mat": api.product(h, name="เสื่อโยคะ หนา 6 มม.", price=490, category_id=sp, description="ออกกำลังที่บ้าน"),
    }
    return h, p, {"el": el, "ki": ki, "sp": sp}


# ------------------------------------------------------------------ deterministic fake embeddings

def test_fake_embed_deterministic_and_normalized(sem_on):
    a = llm.FakeProvider().embed(["หูฟังไร้สาย", "หูฟังไร้สาย", "กระทะ"])
    assert a[0] == a[1] and a[0] != a[2]
    for v in a:
        assert abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-6
    b = llm.FakeProvider().embed(["หูฟังไร้สาย"])
    assert b[0] == a[0]  # ข้ามการเรียกก็ยังได้ค่าเดิม


def test_semantic_results_deterministic(client, catalog, sem_on, monkeypatch):
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    backfill()
    r1 = ids(client, search="earbud")
    r2 = ids(client, search="earbud")
    assert r1 == r2


# ------------------------------------------------------------------ meaning-based ranking

def test_meaning_query_without_keyword_match(client, catalog, sem_on, monkeypatch):
    _, p, _ = catalog
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    backfill()
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    assert ids(client, search="earbud") == []  # keyword หาไม่เจอ
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", True)
    got = ids(client, search="earbud")
    assert got and got[0] in (p["earbuds"]["id"], p["speaker"]["id"])
    assert p["pan"]["id"] not in got and p["mat"]["id"] not in got


def test_keyword_hits_first_then_semantic(client, catalog, sem_on, monkeypatch):
    _, p, _ = catalog
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    monkeypatch.setattr(config, "SEMANTIC_MIN_SCORE", 0.5, raising=False)
    backfill()
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    kw = ids(client, search="หูฟัง")
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", True)
    got = ids(client, search="หูฟัง")
    assert got[:len(kw)] == kw           # ผล keyword เดิมอยู่หน้า ลำดับเดิม
    assert len(got) == len(set(got))     # ไม่ซ้ำ
    assert p["speaker"]["id"] in got[len(kw):]  # semantic ต่อท้าย


def test_semantic_respects_filters(client, catalog, sem_on, monkeypatch):
    h, p, c = catalog
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    backfill()
    assert p["speaker"]["id"] not in ids(client, search="earbud", max_price=1000)
    assert p["earbuds"]["id"] in ids(client, search="earbud", max_price=1000)
    assert ids(client, search="earbud", category_id=c["ki"]) == []
    assert p["speaker"]["id"] not in ids(client, search="earbud", min_price=1600)
    client.delete(f"/api/products/{p['earbuds']['id']}", headers=h)
    assert p["earbuds"]["id"] not in ids(client, search="earbud")


def test_semantic_max_results(client, api, sem_on, monkeypatch):
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    monkeypatch.setattr(config, "SEMANTIC_MAX_RESULTS", 2, raising=False)
    h, _ = api.seller()
    for i in range(5):
        api.product(h, name=f"ลำโพง {i}", description="ฟังเพลง")
    backfill()
    assert len(ids(client, search="earbud")) <= 2


# ------------------------------------------------------------------ degrade to normal search

@pytest.mark.parametrize("mode", ["flag_off", "provider_none", "embed_error", "no_embeddings"])
def test_degrades_to_keyword_results(client, catalog, monkeypatch, mode):
    monkeypatch.setattr(config, "LLM_PROVIDER", "fake")
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    baseline = {q: ids(client, search=q) for q in ("หูฟัง", "earbud", "กระทะ")}
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", True)
    if mode == "flag_off":
        monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    elif mode == "provider_none":
        monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    elif mode == "embed_error":
        backfill()

        def boom(self, texts):
            raise llm.LlmUnavailable("embed down", status=503)
        monkeypatch.setattr(llm.FakeProvider, "embed", boom)
        if hasattr(semantic, "_query_cache"):
            semantic._query_cache.clear()
    # no_embeddings: flag on แต่ยังไม่เคย backfill
    for q, expect in baseline.items():
        assert ids(client, search=q) == expect, (mode, q)


def test_features_reports_semantic(client, monkeypatch):
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    assert client.get("/api/features").json()["semantic_search"] is False


def test_no_new_fields_in_product_list(client, catalog, sem_on, monkeypatch):
    monkeypatch.setattr(llm.FakeProvider, "embed", concept_embed)
    backfill()
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    keys_off = set(client.get("/api/products?search=หูฟัง").json()[0])
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", True)
    for p in client.get("/api/products?search=earbud").json():
        assert set(p) == keys_off
        assert not any("vector" in k or "embed" in k or "score" in k for k in p)


# ------------------------------------------------------------------ refresh only on content change

def _embedding_rows():
    with Session(engine) as s:
        return {e.product_id: (e.text_hash, e.updated_at) for e in s.exec(select(models.ProductEmbedding)).all()}


def test_embedding_refresh_only_on_content_change(client, catalog, sem_on, monkeypatch):
    h, p, _ = catalog
    texts = []
    orig = llm.FakeProvider.embed

    def counting(self, t):
        texts.extend(t)
        return orig(self, t)
    monkeypatch.setattr(llm.FakeProvider, "embed", counting)
    backfill()
    pid = p["pan"]["id"]
    before = _embedding_rows()[pid]
    texts.clear()
    # ราคา / สต็อก เปลี่ยน → ไม่ต้อง embed ใหม่
    client.patch(f"/api/products/{pid}", json={"price": 650, "stock": 3}, headers=h)
    assert _embedding_rows()[pid] == before
    assert not any("กระทะ" in t for t in texts)
    # ชื่อ / รายละเอียด เปลี่ยน → embed ใหม่
    client.patch(f"/api/products/{pid}", json={"description": "ทอดไข่ไม่ติดกระทะ"}, headers=h)
    assert _embedding_rows()[pid][0] != before[0]
    # backfill ซ้ำโดยไม่มีอะไรเปลี่ยน → ไม่ embed ใครเลย
    texts.clear()
    backfill()
    assert texts == []


def test_spec_change_refreshes_embedding(client, api, sem_on):
    from tests.test_phase2_compare import number_attr
    h, _ = api.seller()
    cid = cat_id(client, "electronics")
    num = number_attr(client, cid, "higher")
    p = api.product(h, name="หูฟังสเปก", category_id=cid, attributes=[{"key": num["key"], "value_num": 10}])
    backfill()
    before = _embedding_rows()[p["id"]][0]
    client.patch(f"/api/products/{p['id']}", json={"attributes": [{"key": num["key"], "value_num": 30}]}, headers=h)
    backfill()
    assert _embedding_rows()[p["id"]][0] != before


def test_embedding_failure_never_breaks_product_save(client, api, sem_on, monkeypatch):
    def boom(self, t):
        raise RuntimeError("embed down")
    monkeypatch.setattr(llm.FakeProvider, "embed", boom)
    h, _ = api.seller()
    p = api.product(h, name="สินค้าบันทึกได้แม้ embed พัง")
    r = client.patch(f"/api/products/{p['id']}", json={"name": "ชื่อใหม่"}, headers=h)
    assert r.status_code == 200


# ------------------------------------------------------------------ no user data embedded

def test_no_user_data_embedded(client, api, sem_on, monkeypatch):
    seen = []
    orig = llm.FakeProvider.embed

    def capture(self, t):
        seen.extend(t)
        return orig(self, t)
    monkeypatch.setattr(llm.FakeProvider, "embed", capture)
    hs, _ = api.seller()
    p = api.product(hs, name="หูฟังรีวิวเยอะ", stock=5)
    hb, _, email = api.register_login(name="สมชายผู้ซื้อลับ")
    token = api.user_cart(hb)
    api.add_to_cart(token, p["id"], h=hb)
    body = {"recipient_name": "ผู้รับลับมาก", "recipient_phone": "0899999999", "address": "บ้านเลขที่ลับ 99", "payment_method": "COD"}
    o = client.post(f"/api/orders/checkout?token={token}", json=body, headers=hb).json()[0]
    client.post(f"/api/orders/{o['id']}/ship", headers=hs)
    client.post(f"/api/orders/{o['id']}/receive", headers=hb)
    client.post("/api/reviews", json={"order_item_id": o["items"][0]["id"], "rating": 5, "comment": "รีวิวส่วนตัวลับสุด"}, headers=hb)
    client.patch(f"/api/products/{p['id']}", json={"description": "อัปเดต"}, headers=hs)
    backfill()
    client.get("/api/products?search=earbud")
    blob = " ".join(seen)
    for secret in (email, "สมชายผู้ซื้อลับ", "ผู้รับลับมาก", "0899999999", "บ้านเลขที่ลับ", "รีวิวส่วนตัวลับสุด", token):
        assert secret not in blob, f"ข้อมูลผู้ใช้ถูก embed: {secret}"
    with Session(engine) as s:
        cols = set(models.ProductEmbedding.__table__.columns.keys())
    assert not cols & {"user_id", "email", "query", "search_text"}
