"""จุดเริ่มต้นแอป: เปิด API (prefix /api), เชื่อมฐานข้อมูล, serve ไฟล์ที่อัปโหลด และหน้าเว็บ frontend"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import config, llm, pricing, schemas, specs, storage
from app.database import create_db_and_tables, engine
from app.routers import (
    account, auth, cart, categories, orders, products, reviews, seller, shops, uploads,
)
from app.routers import compare as compare_router
from app.routers import shipping as shipping_router
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ตรวจค่าตั้งค่าที่ห้ามพลาดก่อนรับ request แม้แต่ request เดียว
    # (บน production จะหยุดแอปทันทีถ้า SECRET_KEY ยังเป็นค่า dev)
    config.validate()

    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(
        f"[startup] ที่เก็บไฟล์อัปโหลด: {storage.backend_name()} "
        f"({config.cloudinary_diagnosis()})",
        flush=True,
    )
    create_db_and_tables()
    with Session(engine) as session:
        seed_if_empty(session)
        specs.seed_templates(session)   # แม่แบบสเปกต่อหมวด (upsert ทุกครั้ง)
        # DB เก่าที่มีอยู่ก่อนระบบราคาเฟส 1: เติม price_at_add + ประวัติราคาแถวแรก + sku_price_ref
        # (ทำซ้ำได้ ไม่สร้างข้อมูลซ้ำ — เป็นงานเดียวกับงานกลางคืน)
        pricing.backfill_cart_price_at_add(session)
        result = pricing.nightly_recompute(session)
        print(f"[startup] คำนวณราคาอ้างอิง: {result}", flush=True)
    yield


app = FastAPI(title="ShopMarket API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
def health():
    """ให้บริการ hosting ใช้เช็คว่าแอปยังมีชีวิตอยู่ (health check)

    บอกที่เก็บไฟล์ที่ใช้อยู่ด้วย จะได้ตรวจได้ทันทีหลัง deploy ว่าตั้งค่า Cloudinary ติดหรือยัง
    """
    return {
        "status": "ok",
        "env": config.APP_ENV,
        "storage": storage.backend_name(),
        # บอกเหตุผลว่าทำไมถึงได้ที่เก็บนี้ ช่วยหาสาเหตุตอน deploy โดยไม่ต้องเปิด log
        # (เป็นข้อความอธิบายเท่านั้น ไม่มีค่าลับใดๆ)
        "storage_detail": config.cloudinary_diagnosis(),
    }


@app.get("/api/features", response_model=schemas.Features, tags=["health"])
def features():
    """สวิตช์ฟีเจอร์ให้ frontend ซ่อน/แสดงปุ่ม (เช่น ไม่มี LLM → ซ่อนปุ่มให้ AI ช่วยเติมสเปก)"""
    provider = llm.provider_name() if llm.get_adapter() is not None else "none"
    return schemas.Features(
        spec_suggest=provider != "none",
        llm_provider=provider,
        chat=bool(getattr(config, "CHAT_ENABLED", False)),
        chat_rollout_percent=int(getattr(config, "CHAT_ROLLOUT_PERCENT", 0)),
    )


# ต้อง include API router ก่อน mount static เสมอ
# ไม่งั้น path /api/... จะโดน static files ดักจับก่อนแล้วตอบ 404
app.include_router(auth.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(shops.router, prefix="/api")
app.include_router(cart.router, prefix="/api")
app.include_router(orders.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(seller.router, prefix="/api")
app.include_router(compare_router.router, prefix="/api")
app.include_router(shipping_router.router, prefix="/api")

# ไฟล์รูป/วิดีโอที่ผู้ขายอัปโหลด (ต้อง mount ก่อน "/" ด้วยเหตุผลเดียวกับ API)
app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")



def _frontend_dir() -> str:
    """หาโฟลเดอร์ frontend: Docker = /app/frontend, รันในเครื่อง = <repo>/frontend
    (เดิมอ้าง "frontend" แบบ relative ทำให้ต้องรันจากโฟลเดอร์ที่ถูกเท่านั้น)
    """
    here = Path(__file__).resolve().parent          # .../app
    for candidate in (here.parent / "frontend", here.parent.parent / "frontend"):
        if candidate.is_dir():
            return str(candidate)
    return "frontend"


class _FrontendFiles(StaticFiles):
    """ไฟล์ .html ห้าม browser cache ค้าง (css/js ใช้ ?v= อยู่แล้ว) — หลัง deploy จะได้หน้าใหม่ทันที"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path == "" or path == "." or path.endswith("/") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


# serve ไฟล์ frontend (index.html, pages/, css/, js/) เป็นเว็บหน้าบ้าน
app.mount("/", _FrontendFiles(directory=_frontend_dir(), html=True), name="frontend")
