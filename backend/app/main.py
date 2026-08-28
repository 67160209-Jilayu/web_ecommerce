"""จุดเริ่มต้นแอป: เปิด API (prefix /api), เชื่อมฐานข้อมูล, serve ไฟล์ที่อัปโหลด และหน้าเว็บ frontend"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import config, storage
from app.database import create_db_and_tables, engine
from app.routers import auth, cart, categories, orders, products, reviews, shops, uploads
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ตรวจค่าตั้งค่าที่ห้ามพลาดก่อนรับ request แม้แต่ request เดียว
    # (บน production จะหยุดแอปทันทีถ้า SECRET_KEY ยังเป็นค่า dev)
    config.validate()

    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[startup] ที่เก็บไฟล์อัปโหลด: {storage.backend_name()}", flush=True)
    create_db_and_tables()
    with Session(engine) as session:
        seed_if_empty(session)
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
    }


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

# ไฟล์รูป/วิดีโอที่ผู้ขายอัปโหลด (ต้อง mount ก่อน "/" ด้วยเหตุผลเดียวกับ API)
app.mount("/uploads", StaticFiles(directory=str(config.UPLOAD_DIR)), name="uploads")

# serve ไฟล์ frontend (index.html, pages/, css/, js/) เป็นเว็บหน้าบ้าน
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
