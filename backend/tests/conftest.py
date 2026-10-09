"""ชุดทดสอบ backend — รันบน SQLite ในเครื่อง (ไม่ต้องมี Docker/PostgreSQL)

ข้อจำกัดของ SQLite ที่ชุดทดสอบนี้ครอบคลุมไม่ได้ (ต้องทดสอบบน PostgreSQL จริงภายหลัง):
- `SELECT ... FOR UPDATE` ถูกละทิ้งเงียบๆ → ทดสอบการแย่งซื้อพร้อมกัน (race) ไม่ได้
- SQLite ไม่เก็บ timezone ใน DateTime → ค่าที่อ่านกลับมาเป็น naive datetime
- การ rollback/transaction isolation ระหว่าง connection พร้อมกันไม่เหมือน PostgreSQL
(foreign key เปิดบังคับด้วย PRAGMA ให้ใกล้เคียง PostgreSQL)

วิธีรัน (จากโฟลเดอร์ backend):
    .venv/Scripts/python -m pytest -q
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# ต้องตั้ง env ก่อน import app เพราะ app.config / app.database อ่านค่าตอน import
_TMP = Path(tempfile.mkdtemp(prefix="shopmarket-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
os.environ.setdefault("APP_ENV", "development")
# ห้ามเทสต์เรียก LLM จริงโดยไม่ตั้งใจ (แม้เครื่องจะมี GEMINI_API_KEY) — เทสต์ที่ต้องใช้ให้ monkeypatch เป็น "fake"
# ยกเว้น eval runner ที่สั่ง EVAL_REAL_LLM=1 เอง
if os.environ.get("EVAL_REAL_LLM") != "1":
    os.environ["LLM_PROVIDER"] = "none"
(_TMP / "uploads").mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BACKEND_DIR))
# main.py mount โฟลเดอร์ "frontend" แบบ relative path → ต้อง import จาก root ของ repo
_OLD_CWD = os.getcwd()
os.chdir(REPO_ROOT)

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app import models  # noqa: E402,F401  (ลงทะเบียนตารางทั้งหมดกับ metadata)
from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_if_empty  # noqa: E402
from sqlalchemy import event  # noqa: E402

os.chdir(_OLD_CWD)


@event.listens_for(engine, "connect")
def _sqlite_fk_on(dbapi_conn, _record):
    """PostgreSQL บังคับ foreign key เสมอ แต่ SQLite ปิดไว้โดยค่าเริ่มต้น → เปิดให้เหมือนของจริง"""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@pytest.fixture(autouse=True)
def _fresh_db():
    """ล้างฐานข้อมูลทุก test ให้เป็นอิสระจากกัน"""
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed_if_empty(s)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------- helpers

class Api:
    """ตัวช่วยเรียก API แบบสั้นๆ"""

    def __init__(self, client: TestClient):
        self.c = client

    def register_login(self, email=None, password="pass1234", name="ผู้ทดสอบ"):
        email = email or f"u{uuid.uuid4().hex[:8]}@test.local"
        r = self.c.post("/api/auth/register", json={"email": email, "password": password, "name": name})
        assert r.status_code == 201, r.text
        r = self.c.post("/api/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, r.json(), email

    def user(self, **kw):
        headers, _, _ = self.register_login(**kw)
        return headers

    def seller(self, shop_name=None):
        h = self.user()
        r = self.c.post("/api/shops", json={"name": shop_name or f"shop-{uuid.uuid4().hex[:6]}", "description": ""}, headers=h)
        assert r.status_code == 201, r.text
        return h, r.json()

    def product(self, h, price=1000, stock=10, **kw):
        body = {"name": kw.pop("name", "สินค้าทดสอบ"), "price": price, "stock": stock, **kw}
        r = self.c.post("/api/products", json=body, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    def set_price(self, h, pid, price, **kw):
        r = self.c.patch(f"/api/products/{pid}", json={"price": price, **kw}, headers=h)
        assert r.status_code == 200, r.text
        return r.json()

    def add_to_cart(self, token, pid, qty=1, h=None):
        r = self.c.post(f"/api/cart/{token}/items", json={"product_id": pid, "quantity": qty}, headers=h or {})
        assert r.status_code == 201, r.text
        return r.json()

    def user_cart(self, h):
        """ตะกร้าที่ผูกกับบัญชีแล้ว (merge) → คืน token"""
        token = uuid.uuid4().hex
        r = self.c.post(f"/api/cart/{token}/merge", headers=h)
        assert r.status_code == 200, r.text
        return r.json()["token"]


@pytest.fixture
def api(client):
    return Api(client)


@pytest.fixture
def instant_ref(monkeypatch):
    """ปิดกฎ "ราคาต้องมีผล ≥ 7 วันถึงนับเป็นราคาอ้างอิง" สำหรับเทสต์ที่ทดสอบกฎอื่นผ่าน API ทันที"""
    from app import config
    monkeypatch.setattr(config, "PRICE_REF_MIN_DAYS", 0, raising=False)
