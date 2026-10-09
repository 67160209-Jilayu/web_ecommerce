"""ดัชนี (index) ของตารางหลัก + ensure_schema ต้องรันซ้ำได้ ตรวจด้วย SQLAlchemy inspector

เทียบด้วย "ชุดคอลัมน์" ไม่ผูกกับชื่อ index (ชื่อเปลี่ยนได้) และยอมรับ index ที่คอลัมน์แรกตรง
สำหรับกรณีคอลัมน์เดี่ยว (composite ที่ขึ้นต้นด้วยคอลัมน์นั้นก็ช่วย query ได้)
หมายเหตุ: ทดสอบบน SQLite — PostgreSQL ใช้ CREATE INDEX IF NOT EXISTS ชุดเดียวกัน แต่ไม่ได้รันจริงที่นี่
"""
import pytest
from sqlalchemy import inspect, text

from app import database
from app.database import engine

SINGLE = [
    ("product", "shop_id"),
    ("product", "category_id"),
    ("productmedia", "product_id"),
    ("cartitem", "cart_id"),
    ("cartitem", "product_id"),
    ("cart", "user_id"),
    ("orderitem", "order_id"),
    ("orderitem", "product_id"),
]
COMPOSITE = [("product", ["is_active", "category_id"])]


def _indexes(table):
    insp = inspect(engine)
    out = [list(ix["column_names"]) for ix in insp.get_indexes(table)]
    # unique constraint ก็ใช้เป็น index ได้
    out += [list(uc["column_names"]) for uc in insp.get_unique_constraints(table)]
    pk = insp.get_pk_constraint(table)
    if pk and pk.get("constrained_columns"):
        out.append(list(pk["constrained_columns"]))
    return out


def _has_leading(table, column):
    return any(cols and cols[0] == column for cols in _indexes(table))


@pytest.mark.parametrize("table,column", SINGLE, ids=[f"{t}.{c}" for t, c in SINGLE])
def test_index_exists(table, column):
    assert _has_leading(table, column), f"{table}.{column} ไม่มี index — มีอยู่: {_indexes(table)}"


@pytest.mark.parametrize("table,cols", COMPOSITE, ids=[f"{t}({','.join(c)})" for t, c in COMPOSITE])
def test_composite_index_exists(table, cols):
    assert cols in _indexes(table), f"{table} ไม่มี composite {cols} — มีอยู่: {_indexes(table)}"


def test_index_names_unique_and_prefixed_sanely():
    """ชื่อ index ต้องไม่ซ้ำกันทั้งฐานข้อมูล (SQLite/PostgreSQL ใช้ namespace ระดับ schema)"""
    insp = inspect(engine)
    names = [ix["name"] for t in insp.get_table_names() for ix in insp.get_indexes(t)]
    assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]


def test_ensure_schema_idempotent():
    before = {t: sorted(map(tuple, _indexes(t))) for t, _ in SINGLE}
    database.ensure_schema()
    database.ensure_schema()
    database.create_db_and_tables()
    after = {t: sorted(map(tuple, _indexes(t))) for t, _ in SINGLE}
    assert before == after
    # คอลัมน์ที่ ALTER เพิ่มทีหลังยังอยู่ครบและไม่ซ้ำ
    for table, column, _ in database.ADDED_COLUMNS:
        cols = [c["name"] for c in inspect(engine).get_columns(table)]
        assert cols.count(column) == 1, (table, column)


def test_ensure_schema_recreates_missing_indexes_on_legacy_db():
    """DB เก่าที่สร้างก่อนมี index: create_all ไม่เพิ่ม index ให้ตารางเดิม → ensure_schema ต้องเติมให้เอง"""
    insp = inspect(engine)
    dropped = []
    with engine.begin() as conn:
        for table, _ in SINGLE + [(t, None) for t, _ in COMPOSITE]:
            for ix in insp.get_indexes(table):
                if ix["name"] and not ix.get("unique"):
                    conn.execute(text(f'DROP INDEX IF EXISTS "{ix["name"]}"'))
                    dropped.append(ix["name"])
    assert dropped, "ไม่มี index ให้ลบ — ทดสอบนี้ไม่มีความหมาย"
    database.ensure_schema()
    for table, column in SINGLE:
        assert _has_leading(table, column), f"ensure_schema ไม่ได้สร้าง index {table}.{column} ให้ DB เก่า"
    for table, cols in COMPOSITE:
        assert cols in _indexes(table)
    database.ensure_schema()  # รันซ้ำหลังสร้างแล้วต้องไม่พัง


# ------------------------------------------------------------------ ตามชื่อใน EXTRA_INDEXES (single source of truth)

def test_every_extra_index_present_by_name_and_columns():
    from app.models import EXTRA_INDEXES

    assert len(EXTRA_INDEXES) >= 9
    insp = inspect(engine)
    for table, name, cols in EXTRA_INDEXES:
        by_name = {ix["name"]: ix for ix in insp.get_indexes(table)}
        assert name in by_name, f"ขาด index {name} บน {table}: {sorted(by_name)}"
        assert list(by_name[name]["column_names"]) == cols, (name, by_name[name]["column_names"])
    comp = next(c for t, n, c in EXTRA_INDEXES if n == "ix_product_is_active_category_id")
    assert comp == ["is_active", "category_id"]


def test_ensure_schema_recreates_by_name_after_drop():
    from app.models import EXTRA_INDEXES

    with engine.begin() as conn:
        for _, name, _ in EXTRA_INDEXES:
            conn.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
    insp = inspect(engine)
    assert not any(n in {i["name"] for i in insp.get_indexes(t)} for t, n, _ in EXTRA_INDEXES)
    database.ensure_schema()
    database.ensure_schema()
    insp = inspect(engine)
    for table, name, _ in EXTRA_INDEXES:
        assert name in {i["name"] for i in insp.get_indexes(table)}, name


_OLD_SCHEMA = """
CREATE TABLE user (id INTEGER PRIMARY KEY, email VARCHAR, name VARCHAR, hashed_password VARCHAR, created_at DATETIME);
CREATE TABLE shop (id INTEGER PRIMARY KEY, owner_id INTEGER, name VARCHAR, description VARCHAR, rating FLOAT, review_count INTEGER, is_verified BOOLEAN, created_at DATETIME);
CREATE TABLE category (id INTEGER PRIMARY KEY, name VARCHAR, slug VARCHAR, icon VARCHAR);
CREATE TABLE product (id INTEGER PRIMARY KEY, shop_id INTEGER, category_id INTEGER, name VARCHAR, price INTEGER, original_price INTEGER, description VARCHAR, stock INTEGER, free_shipping BOOLEAN, image VARCHAR, cover_url VARCHAR, rating FLOAT, review_count INTEGER, sold INTEGER, is_active BOOLEAN, created_at DATETIME);
CREATE TABLE productmedia (id INTEGER PRIMARY KEY, product_id INTEGER, url VARCHAR, media_type VARCHAR, sort_order INTEGER);
CREATE TABLE cart (id INTEGER PRIMARY KEY, token VARCHAR, user_id INTEGER);
CREATE TABLE cartitem (id INTEGER PRIMARY KEY, cart_id INTEGER, product_id INTEGER, quantity INTEGER);
CREATE TABLE "order" (id INTEGER PRIMARY KEY, order_number VARCHAR, buyer_id INTEGER, shop_id INTEGER, status VARCHAR, payment_method VARCHAR, subtotal INTEGER, shipping_fee INTEGER, total INTEGER, recipient_name VARCHAR, recipient_phone VARCHAR, address VARCHAR, note VARCHAR, created_at DATETIME, paid_at DATETIME, shipped_at DATETIME, delivered_at DATETIME, cancelled_at DATETIME);
CREATE TABLE orderitem (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name VARCHAR, product_price INTEGER, product_image VARCHAR, product_cover_url VARCHAR, quantity INTEGER, subtotal INTEGER);
"""

_RUNNER = r"""
import json, sys
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from app.main import app
from app.database import engine
from app.models import EXTRA_INDEXES
out = []
for run in (1, 2):
    with TestClient(app) as c:
        health = c.get("/api/health").status_code
        cats = len(c.get("/api/categories").json())
    insp = inspect(engine)
    missing = [n for t, n, _ in EXTRA_INDEXES if n not in {i["name"] for i in insp.get_indexes(t)}]
    cols = {c["name"] for c in insp.get_columns("cartitem")} | {c["name"] for c in insp.get_columns("product")}
    out.append({"run": run, "missing": missing, "health": health, "cats": cats,
                "has_new_cols": {"price_at_add", "brand", "barcode"} <= cols})
print("RESULT" + json.dumps(out))
"""


def test_startup_twice_on_legacy_database_file(tmp_path):
    """DB เก่าที่ไม่มี index เลย (เหมือน Render ก่อนอัปเดต): สตาร์ตแอป 2 รอบต้องสร้าง index ครบและไม่ error"""
    import json
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path

    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(_OLD_SCHEMA)
    con.commit()
    con.close()

    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{db.as_posix()}", UPLOAD_DIR=str(tmp_path / "up"),
               PYTHONUTF8="1", PYTHONPATH=str(backend), LLM_PROVIDER="none")
    r = subprocess.run([sys.executable, "-c", _RUNNER], cwd=str(backend.parent), env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    line = next(l for l in r.stdout.splitlines() if l.startswith("RESULT"))
    runs = json.loads(line[len("RESULT"):])
    assert [x["run"] for x in runs] == [1, 2]
    for x in runs:
        assert x["missing"] == [], x
        assert x["health"] == 200 and x["cats"] == 6 and x["has_new_cols"], x
