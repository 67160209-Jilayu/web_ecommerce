"""จุดเริ่มต้นแอป: เปิด API (prefix /api) และ serve หน้าเว็บ frontend (static files) ในตัวเดียว"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import products

app = FastAPI(title="ShopMarket API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ต้อง include API router ก่อน mount static เสมอ
# ไม่งั้น path /api/... จะโดน static files ดักจับก่อนแล้วตอบ 404
app.include_router(products.router, prefix="/api")

# serve ไฟล์ frontend (index.html, pages/, css/, js/) เป็นเว็บหน้าบ้าน
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
