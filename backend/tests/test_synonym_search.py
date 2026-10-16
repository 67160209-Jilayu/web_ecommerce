"""ค้นหา: fallback คำพ้อง/ภาษาพูด (match="synonym") — ทำงานเฉพาะเมื่อ keyword ได้ผลน้อย ไม่ขยับลำดับ keyword"""
import pytest

from app import config

pytest.importorskip("app.synonyms")
from app import synonyms  # noqa: E402


def search(client, **params):
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/products?{q}")
    assert r.status_code == 200, r.text
    return r.json()


def by_id(items):
    return {p["id"]: p.get("match") for p in items}


@pytest.fixture
def rain(api):
    h, _ = api.seller()
    return h, {
        "umbrella": api.product(h, name="ร่มพับกันฝน", price=250, stock=5),
        "coat": api.product(h, name="เสื้อกันฝนเด็ก", price=180, stock=5),
        "pan": api.product(h, name="กระทะเคลือบ", price=690, stock=5),
    }


def test_synonym_hits_tagged_and_unrelated_excluded(client, rain):
    _, p = rain
    items = search(client, search="ของใช้หน้าฝน")
    m = by_id(items)
    assert m[p["umbrella"]["id"]] == "synonym" and m[p["coat"]["id"]] == "synonym"
    assert p["pan"]["id"] not in m


def test_keyword_hit_is_tagged_keyword_no_synonym_needed(client, api):
    h, _ = api.seller()
    ps = [api.product(h, name=f"ร่มพับ รุ่น {i}", price=100 + i) for i in range(3)]
    items = search(client, search="ร่ม")
    assert {p["id"] for p in items} >= {p["id"] for p in ps}
    assert all(p.get("match") in (None, "keyword") for p in items)


def test_keyword_hits_first_in_original_order(client, api, monkeypatch):
    h, _ = api.seller()
    kw = api.product(h, name="ของใช้หน้าฝน ชุดพิเศษ", price=900, stock=5)
    syn = api.product(h, name="ร่มพับกันฝน", price=100, stock=5)
    items = search(client, search="ของใช้หน้าฝน")
    ids = [p["id"] for p in items]
    assert ids.index(kw["id"]) < ids.index(syn["id"])
    m = by_id(items)
    assert m[kw["id"]] in (None, "keyword") and m[syn["id"]] == "synonym"
    # เทียบกับตอนปิด fallback: ลำดับ keyword เหมือนเดิมทุกตัว
    monkeypatch.setattr(config, "SYNONYM_FALLBACK", False)
    assert [p["id"] for p in search(client, search="ของใช้หน้าฝน")] == [kw["id"]]


def test_not_used_when_enough_keyword_results(client, api):
    h, _ = api.seller()
    for i in range(config.SYNONYM_MIN_RESULTS):
        api.product(h, name=f"ของใช้หน้าฝน แบบที่ {i}", price=100 + i)
    syn = api.product(h, name="ร่มพับกันฝน", price=100)
    assert syn["id"] not in [p["id"] for p in search(client, search="ของใช้หน้าฝน")]


def test_threshold_configurable(client, api, monkeypatch):
    h, _ = api.seller()
    api.product(h, name="ของใช้หน้าฝน ชุดเดียว", price=100)
    syn = api.product(h, name="ร่มพับกันฝน", price=100)
    monkeypatch.setattr(config, "SYNONYM_MIN_RESULTS", 1)
    assert syn["id"] not in [p["id"] for p in search(client, search="ของใช้หน้าฝน")]
    monkeypatch.setattr(config, "SYNONYM_MIN_RESULTS", 5)
    assert syn["id"] in [p["id"] for p in search(client, search="ของใช้หน้าฝน")]


def test_flag_off_equals_plain_search(client, rain, monkeypatch):
    monkeypatch.setattr(config, "SYNONYM_FALLBACK", False)
    assert search(client, search="ของใช้หน้าฝน") == []


def test_filters_still_apply(client, api, rain):
    h, p = rain
    cheap_only = {x["id"] for x in search(client, search="ของใช้หน้าฝน", max_price=200)}
    assert cheap_only == {p["coat"]["id"]}
    assert search(client, search="ของใช้หน้าฝน", min_price=1000) == []
    assert search(client, search="หน้าฝน", category_id=999999) == []
    client.delete(f"/api/products/{p['coat']['id']}", headers=h)
    assert p["coat"]["id"] not in [x["id"] for x in search(client, search="ของใช้หน้าฝน")]


def test_works_without_llm_or_semantic(client, rain, monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "none")
    monkeypatch.setattr(config, "SEMANTIC_SEARCH", False)
    assert any(v == "synonym" for v in by_id(search(client, search="ของใช้หน้าฝน")).values())


def test_synonym_table_monkeypatchable_and_matches_brand_description(client, api, monkeypatch):
    monkeypatch.setitem(synonyms.SYNONYMS, "ทีวีจอแบน", ["โทรทัศน์"])
    h, _ = api.seller()
    a = api.product(h, name="Acme 43 นิ้ว", description="โทรทัศน์ดิจิทัล", price=9000)
    b = api.product(h, name="โทรทัศน์ 32 นิ้ว", price=5000)
    c = api.product(h, name="หม้อหุงข้าว", price=900)
    m = by_id(search(client, search="ทีวีจอแบน"))
    assert m[a["id"]] == "synonym" and m[b["id"]] == "synonym" and c["id"] not in m


def test_whitespace_in_query_ignored(client, rain):
    m = by_id(search(client, search="ของใช้ หน้า ฝน"))
    assert any(v == "synonym" for v in m.values())


def test_no_duplicates_and_no_error_on_odd_queries(client, rain):
    for q in ("ของใช้หน้าฝน", "%25", "'; DROP TABLE product; --", "ก" * 200):
        ids = [p["id"] for p in search(client, search=q)]
        assert len(ids) == len(set(ids))


def test_no_extra_fields_leak(client, rain):
    for p in search(client, search="ของใช้หน้าฝน"):
        assert not any(k in p for k in ("score", "vector", "embedding", "synonyms"))
