# ShopMarket — Marketplace ค้นหาและสั่งซื้อสินค้า

โปรเจกต์จาก User Journey ข้อ 2 (อีคอมเมิร์ซ) ทำตามแนวทาง "จาก User Journey สู่โค้ดจริงด้วย AI"

**ตอนนี้อยู่สัปดาห์ 1** — scaffold รันได้ในเครื่อง มีหน้าจอหลัก 3 หน้า backend คืน mock data ยังไม่ต่อ DB จริงและยังไม่ deploy

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: HTML + CSS + JS ธรรมดา ไม่มี framework
- Database: PostgreSQL ผ่าน Docker Compose (ยังไม่ได้ใช้จริงสัปดาห์นี้)
- รันทั้งระบบด้วย Docker + Docker Compose

## วิธีรัน (ต้องมี Docker Desktop)

```bash
cp .env.example .env
docker compose up
```

เปิดดูที่:
- เว็บ: http://localhost:8000
- API docs: http://localhost:8000/docs

ปิดด้วย `docker compose down`

> ต้องรันผ่าน Docker เท่านั้น รัน `uvicorn` ตรงๆ นอก container ไม่ได้ เพราะ path โฟลเดอร์ `frontend` อ้างอิงตาม `WORKDIR /app` ใน Dockerfile

## โครงสร้างโปรเจกต์
```
backend/app/main.py                 จุดเริ่มแอป: API router + mount static files
backend/app/routers/products.py     API สินค้า (GET /api/products, GET /api/products/{id}) — mock data
frontend/index.html                 หน้าค้นหา + รายการสินค้า
frontend/pages/product-detail.html  หน้ารายละเอียดสินค้า + เพิ่มตะกร้า
frontend/pages/cart.html            หน้าตะกร้าสินค้า
docs/user-journey.md                User Journey ที่ใช้อ้างอิง
docs/api-spec.md                    รายการ API endpoint
```


## Edge Cases ที่ทำแล้ว
- สินค้าหมด → ปิดปุ่มสั่งซื้อ, badge "สินค้าหมด"
- สต็อกเหลือน้อย (≤5) → แจ้งเตือน
- ค้นหาไม่พบ → แสดงข้อความแทนหน้าว่าง
- จำกัดจำนวนในตะกร้าไม่เกิน stock

ที่เหลือ (รอสัปดาห์ 2-3) ดูใน [docs/user-journey.md](docs/user-journey.md)

## Prompt ที่ใช้ (แยกตามสัปดาห์)

### สัปดาห์ 1 — Frontend scaffold (ทำแล้ว)
> สร้าง FastAPI backend ที่ serve static frontend ในตัวเดียว มี router `products.py` คืน mock data
> ตาม User Journey "อีคอมเมิร์ซ — Marketplace: ค้นหาและสั่งซื้อสินค้า" พร้อมหน้า HTML 3 หน้า
> (ค้นหา/รายการสินค้า, รายละเอียดสินค้า, ตะกร้าสินค้า) เรียก API ด้วย `fetch()` และรองรับ
> Edge Case: สินค้าหมด, สต็อกใกล้หมด, ค้นหาไม่พบ




## Deploy URL
_ยังไม่ deploy — จะใส่ลิงก์ตรงนี้หลังต่อ hosting_
