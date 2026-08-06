# ShopMarket — Marketplace ค้นหาและสั่งซื้อสินค้า
67160209 จิรายุ สกุลวงศ์นาวี
67160207 กิตติพศ ระบาย
โปรเจกต์จาก User Journey ข้อ 2 (อีคอมเมิร์ซ) ทำตามแนวทาง "จาก User Journey สู่โค้ดจริงด้วย AI"

**ตอนนี้อยู่สัปดาห์ 4** — มีระบบสมัคร/ล็อกอิน (JWT) แล้ว endpoint ที่แก้ไขข้อมูลต้องล็อกอินก่อน ยังไม่ deploy

## Tech Stack
- Backend: FastAPI (Python)
- Frontend: HTML + CSS + JS ธรรมดา ไม่มี framework
- Database: PostgreSQL ผ่าน Docker Compose (ต่อจริงแล้ว ใช้ SQLModel)
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
backend/app/main.py                 จุดเริ่มแอป: API router + เชื่อม DB + mount static files
backend/app/database.py             เชื่อมต่อ PostgreSQL (SQLModel engine/session)
backend/app/models.py               โครงสร้างตาราง Shop, Product, Cart, CartItem, User
backend/app/schemas.py              รูปแบบข้อมูลรับ-ส่งผ่าน API
backend/app/crud.py                 ฟังก์ชันอ่าน/เขียนฐานข้อมูล
backend/app/auth.py                 hash รหัสผ่าน + ออก/ตรวจสอบ JWT token
backend/app/seed.py                 ใส่ข้อมูลตัวอย่างตอนเริ่มระบบครั้งแรก
backend/app/routers/products.py     API สินค้า (GET/POST /api/products) — POST ต้องล็อกอิน
backend/app/routers/shops.py        API ร้านค้า (GET/POST /api/shops) — POST ต้องล็อกอิน
backend/app/routers/cart.py         API ตะกร้าสินค้า (GET/POST/PATCH/DELETE)
backend/app/routers/auth.py         API สมัคร/ล็อกอิน (register/login/me)
frontend/index.html                 หน้าค้นหา + รายการสินค้า
frontend/pages/product-detail.html  หน้ารายละเอียดสินค้า + เพิ่มตะกร้า (เรียก API จริง)
frontend/pages/cart.html            หน้าตะกร้าสินค้า (เรียก API จริง ไม่ใช้ localStorage แล้ว)
frontend/pages/login.html           หน้าสมัครสมาชิก/เข้าสู่ระบบ
docs/user-journey.md                User Journey ที่ใช้อ้างอิง
docs/er-diagram.md                  โครงสร้างตาราง + ความสัมพันธ์
docs/api-spec.md                    รายการ API endpoint
```


## Edge Cases ที่ทำแล้ว
- สินค้าหมด → ปิดปุ่มสั่งซื้อ, badge "สินค้าหมด"
- สต็อกเหลือน้อย (≤5) → แจ้งเตือน
- ค้นหาไม่พบ → แสดงข้อความแทนหน้าว่าง
- จำกัดจำนวนในตะกร้าไม่เกิน stock (เช็คที่ backend จริงแล้ว ไม่ใช่แค่ฝั่ง frontend)
- ตะกร้าผูกกับ browser ผ่าน token ใน localStorage (คนละเครื่อง/เบราว์เซอร์ = คนละตะกร้า)
- **สินค้าหมดสต็อกระหว่างลูกค้ากำลังเช็คเอาท์** (จากเอกสาร User Journey) → ล็อก row สินค้าไว้ระหว่าง
  transaction ตอนเพิ่มลงตะกร้า กันสองคำขอพร้อมกันอ่าน stock ค่าเดิมแล้วเผลอเกินจำนวนจริง (race condition)
- สมัครสมาชิกด้วยอีเมลซ้ำ → 400 พร้อมข้อความชัดเจน
- ล็อกอินด้วยอีเมล/รหัสผ่านผิด → 401 พร้อมข้อความชัดเจน
- เรียก endpoint ที่ต้องล็อกอินโดยไม่มี/token หมดอายุ → 401 เสมอ

ที่เหลือ (รอสัปดาห์ 5) ดูใน [docs/user-journey.md](docs/user-journey.md)

## Prompt ที่ใช้ (แยกตามสัปดาห์)

### สัปดาห์ 1 — Frontend scaffold (ทำแล้ว)
> สร้าง FastAPI backend ที่ serve static frontend ในตัวเดียว มี router `products.py` คืน mock data
> ตาม User Journey "อีคอมเมิร์ซ — Marketplace: ค้นหาและสั่งซื้อสินค้า" พร้อมหน้า HTML 3 หน้า
> (ค้นหา/รายการสินค้า, รายละเอียดสินค้า, ตะกร้าสินค้า) เรียก API ด้วย `fetch()` และรองรับ
> Edge Case: สินค้าหมด, สต็อกใกล้หมด, ค้นหาไม่พบ

### สัปดาห์ 2 — Database + Backend จริง (ทำแล้ว)
> จาก User Journey นี้ ช่วยออกแบบ Database Schema โดยใช้ SQLModel (Python) แยก entity Shop
> กับ Product ออกจากกัน (ความสัมพันธ์ one-to-many) เพราะ Pain Point ในเอกสารบอกว่าลูกค้า
> "ไม่รู้จะเชื่อร้านไหน" จากนั้นย้าย endpoint `GET /api/products`, `GET /api/products/{id}`
> จาก mock data ไปอ่าน/เขียนจาก PostgreSQL จริง พร้อมเพิ่ม `POST /api/products` และ
> router `shops.py` (`GET`/`POST /api/shops`) โดยคง response shape เดิมไว้ (field `shop_name`
> แบบ flatten) เพื่อไม่ต้องแก้ frontend ที่เขียนไว้ตั้งแต่สัปดาห์ 1

### สัปดาห์ 3 — เชื่อม frontend กับ backend จริง (ทำแล้ว)
> ย้ายตะกร้าสินค้าจาก localStorage ไปเป็นตาราง Cart/CartItem จริงใน PostgreSQL โดยที่ยังไม่มี
> ระบบล็อกอิน ให้ frontend สร้าง token (UUID) เก็บใน localStorage เองแล้วส่งไปผูกกับตะกร้าใน DB
> แทน user_id ชั่วคราว เพิ่ม router `cart.py` ครบ CRUD (`GET/POST /api/cart/{token}`,
> `PATCH`/`DELETE /api/cart/{token}/items/{product_id}`) แล้วแก้ `js/api.js`,
> `product-detail.html`, `cart.html` ให้เรียก API จริงแทนฟังก์ชัน localStorage เดิมทั้งหมด
> โดยคง UI/UX เดิมไว้ไม่เปลี่ยน

### สัปดาห์ 4 — ระบบล็อกอิน + Edge Case เพิ่ม (ทำแล้ว)
> เพิ่มระบบสมัคร/ล็อกอินด้วย JWT ตามมาตรฐาน OAuth2PasswordBearer ของ FastAPI (ใช้ bcrypt เข้ารหัส
> รหัสผ่าน) สร้าง router `auth.py` (`register`/`login`/`me`) แล้วเอา dependency
> `get_current_user` ไปผูกกับ `POST /api/products` และ `POST /api/shops` ให้ต้องล็อกอินก่อนถึงจะ
> เรียกได้ พร้อมทำหน้า `login.html` (สมัคร/เข้าสู่ระบบในหน้าเดียว) และแสดงสถานะล็อกอินที่ header
> ทุกหน้า จากนั้นแก้ Edge Case จากเอกสาร User Journey เรื่อง "สินค้าหมดสต็อกระหว่างลูกค้ากำลัง
> เช็คเอาท์" โดยเพิ่ม row-level lock (`SELECT ... FOR UPDATE`) ตอนเพิ่มสินค้าลงตะกร้า กัน race
> condition เวลามีคำขอพร้อมกันหลายคำขอแย่งสินค้าที่เหลือน้อย

## Deploy URL
_ยังไม่ deploy — จะใส่ลิงก์ตรงนี้หลังต่อ hosting_
