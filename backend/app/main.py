"""จุดเริ่มต้นแอป: เปิด API (prefix /api), เชื่อมฐานข้อมูล, และ serve หน้าเว็บ frontend ในตัวเดียว"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.database import create_db_and_tables, engine
from app.routers import cart, products, shops
from app.seed import seed_if_empty


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    with Session(engine) as session:
        seed_if_empty(session)
    yield


app = FastAPI(title="ShopMarket API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ต้อง include API router ก่อน mount static เสมอ
# ไม่งั้น path /api/... จะโดน static files ดักจับก่อนแล้วตอบ 404
app.include_router(products.router, prefix="/api")
app.include_router(shops.router, prefix="/api")
app.include_router(cart.router, prefix="/api")

# serve ไฟล์ frontend (index.html, pages/, css/, js/) เป็นเว็บหน้าบ้าน
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
