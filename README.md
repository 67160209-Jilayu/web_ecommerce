# ShopMarket — Marketplace ค้นหาและสั่งซื้อสินค้า

โปรเจกต์ตัวอย่างจาก User Journey ข้อ 2 (อีคอมเมิร์ซ) ในเอกสาร "User Journeys: ระบบดิจิทัลตามอุตสาหกรรมหลักของประเทศไทย"
พัฒนาตามโครงสร้างกิจกรรม "จาก User Journey สู่โค้ดจริงด้วย AI"

**สถานะปัจจุบัน: สัปดาห์ 1 (Kickoff)** — scaffold รันได้ในเครื่อง, มีหน้าจอหลัก 3 หน้า, backend คืนค่า mock data
ยังไม่เชื่อมฐานข้อมูลจริงและยังไม่ deploy

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: HTML + CSS + JavaScript ธรรมดา (ไม่มี framework)
- Database: PostgreSQL (รันผ่าน Docker Compose — ยังไม่ได้เชื่อมต่อใช้งานจริงในสัปดาห์นี้)
- รันทั้งระบบด้วย Docker + Docker Compose

## วิธีรันโปรเจกต์ (ต้องติดตั้ง Docker Desktop ก่อน)

```bash
cp .env.example .env
docker compose up
```

จากนั้นเปิดเบราว์เซอร์:
- หน้าเว็บ: http://localhost:8000
- Swagger API docs: http://localhost:8000/docs

ปิดระบบด้วย:
```bash
docker compose down
```

> **หมายเหตุ**: โปรเจกต์นี้ออกแบบให้รันผ่าน Docker เท่านั้น (ไม่รองรับการรัน `uvicorn` ตรงๆ นอก
> container เพราะ path ของโฟลเดอร์ `frontend` ที่ FastAPI ใช้ mount เป็น static files อ้างอิงตาม
> `WORKDIR /app` ใน Dockerfile)

## โครงสร้างโปรเจกต์
```
backend/app/main.py           จุดเริ่มแอป: include API router + mount static files (frontend)
backend/app/routers/products.py   API สินค้า (GET /api/products, GET /api/products/{id}) — mock data
frontend/index.html            หน้าค้นหา + รายการสินค้า
frontend/pages/product-detail.html  หน้ารายละเอียดสินค้า + เพิ่มลงตะกร้า
frontend/pages/cart.html       หน้าตะกร้าสินค้า
docs/user-journey.md           User Journey ที่ใช้อ้างอิง (Persona, ขั้นตอน, Edge Case, Acceptance Criteria)
docs/api-spec.md               รายการ API endpoint ทั้งหมด
```

## หน้าจอที่ทำในสัปดาห์นี้ (อ้างอิง [docs/user-journey.md](docs/user-journey.md))
1. หน้าค้นหา/รายการสินค้า (`index.html`) — ค้นหาด้วยคำ, แสดง badge ส่งฟรี/สินค้าหมด
2. หน้ารายละเอียดสินค้า (`pages/product-detail.html`) — เลือกจำนวน, เพิ่มลงตะกร้า, เตือนสต็อกใกล้หมด
3. หน้าตะกร้าสินค้า (`pages/cart.html`) — ปรับจำนวน/ลบสินค้า, คำนวณยอดรวม (เก็บใน localStorage ชั่วคราว)

## Edge Cases ที่รองรับแล้ว
- สินค้าหมดสต็อก → ปิดปุ่มสั่งซื้อ, แสดง badge "สินค้าหมด"
- สต็อกเหลือน้อย (≤5 ชิ้น) → แสดงข้อความเตือน
- ค้นหาไม่พบสินค้า → แสดงข้อความแทนหน้าว่างเปล่า
- จำกัดจำนวนที่เพิ่มในตะกร้าไม่ให้เกิน stock คงเหลือ

รายละเอียดเพิ่มเติมและ Edge Case ที่ยังไม่ทำ (รอสัปดาห์ 2-3) ดูใน [docs/user-journey.md](docs/user-journey.md)

## Prompt ที่ใช้ (บันทึกไว้สำหรับสัปดาห์ถัดไป)
> สร้าง FastAPI backend ที่ serve static frontend (HTML/CSS/JS ธรรมดา) ในตัวเดียว โดยมี router
> `products.py` คืนค่า mock data สินค้าตาม User Journey "อีคอมเมิร์ซ — Marketplace: ค้นหาและสั่งซื้อสินค้า"
> พร้อมสร้างหน้า HTML 3 หน้า (ค้นหา/รายการสินค้า, รายละเอียดสินค้า, ตะกร้าสินค้า) ที่เรียก API ด้วย
> `fetch()` และรองรับ Edge Case: สินค้าหมดสต็อก, สต็อกใกล้หมด, ค้นหาไม่พบสินค้า

## Roadmap ถัดไป
- **สัปดาห์ 2**: ออกแบบ ER diagram, เขียน SQLModel models, เชื่อม endpoint กับ PostgreSQL จริง
- **สัปดาห์ 3**: เปลี่ยนตะกร้าจาก localStorage ไปผูกกับ backend + ผู้ใช้จริง
- **สัปดาห์ 4**: ระบบล็อกอิน/สิทธิ์ผู้ใช้ + จัดการ Edge Case เพิ่มเติม
- **สัปดาห์ 5**: Deploy เวอร์ชันเต็ม (Render/Railway) + usability test
- **สัปดาห์ 6**: ปรับปรุงจาก feedback + นำเสนอ

## Deploy URL
_ยังไม่ deploy — จะอัปเดตลิงก์ที่นี่หลังเชื่อมต่อบริการ hosting (Render/Railway) ในขั้นถัดไป_
