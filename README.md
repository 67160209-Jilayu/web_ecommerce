67160209 จิรายุ สกุลวงศ์นาวี
67160207 กิตติพศ ระบาย
# ShopMarket — Marketplace ซื้อ-ขายออนไลน์



## Tech Stack
- Backend: FastAPI (Python) + SQLModel
- Frontend: HTML + CSS + JS ธรรมดา ไม่มี framework
- Database: PostgreSQL
- รันทั้งระบบด้วย Docker + Docker Compose

## วิธีรัน (ต้องมี Docker Desktop)

```bash
cp .env.example .env
docker compose up -d --build
```

เปิดดูที่:
- เว็บ: http://localhost:8000
- API docs: http://localhost:8000/docs

ปิดด้วย `docker compose down`

> **ถ้าเจอ error `column ... does not exist`** แปลว่าโครงสร้างตารางใน DB เก่าไม่ตรงกับโค้ดปัจจุบัน
> (โปรเจกต์ยังไม่มีระบบ migration) แก้ด้วย `docker compose down -v` แล้ว `docker compose up -d --build` ใหม่

> ต้องรันผ่าน Docker เท่านั้น รัน `uvicorn` ตรงๆ นอก container ไม่ได้ เพราะ path โฟลเดอร์ `frontend`
> และ `uploads` อ้างอิงตาม `WORKDIR /app` ใน Dockerfile

### บัญชีตัวอย่างสำหรับทดลอง
| อีเมล | รหัสผ่าน | ร้าน |
|---|---|---|
| mango@shopmarket.test | mango1234 | mango |

ระบบไม่มีสินค้าตัวอย่างมาให้ — ล็อกอินด้วยบัญชีนี้แล้วกด "ร้านของฉัน → ลงขายสินค้าใหม่"
เพื่อเพิ่มสินค้าเอง หรือสมัครบัญชีใหม่แล้วเปิดร้านของตัวเองก็ได้

## ฟีเจอร์หลัก

**ฝั่งผู้ซื้อ**
- ค้นหา / กรองตามหมวดหมู่ / กรองช่วงราคา / เรียงตามราคา-ยอดขาย-คะแนน
- ดูรายละเอียดสินค้าพร้อมแกลเลอรีรูปและวิดีโอ + อ่านรีวิวจากผู้ซื้อจริง
- ตะกร้าสินค้า (guest ก็ใช้ได้ พอล็อกอินตะกร้าจะถูกผูกเข้าบัญชีให้อัตโนมัติ)
- สั่งซื้อ เลือกวิธีชำระเงิน 3 ช่องทาง ติดตามสถานะ ยกเลิก และรีวิวหลังได้รับของ

**ฝั่งผู้ขาย**
- เปิดร้านฟรี (1 บัญชี 1 ร้าน)
- ลงขายสินค้า อัปโหลดรูป/วิดีโอ (ลากไฟล์มาวางได้) แก้ไข ปิดขาย
- แดชบอร์ดดูสินค้าทั้งหมด รับคำสั่งซื้อ กดจัดส่ง ยกเลิก
- ดูคะแนนรีวิวร้านที่คำนวณจากรีวิวจริง

## โครงสร้างโปรเจกต์
```
backend/app/main.py                 จุดเริ่มแอป: API router + เชื่อม DB + serve uploads/frontend
backend/app/database.py             เชื่อมต่อ PostgreSQL (SQLModel engine/session)
backend/app/models.py               ตาราง: User, Shop, Category, Product, ProductMedia,
                                    Cart, CartItem, Order, OrderItem, Review
backend/app/schemas.py              รูปแบบข้อมูลรับ-ส่งผ่าน API
backend/app/crud.py                 business logic ทั้งหมด (checkout, สิทธิ์, คำนวณ rating)
backend/app/auth.py                 hash รหัสผ่าน (bcrypt) + ออก/ตรวจสอบ JWT
backend/app/seed.py                 ข้อมูลตั้งต้น: หมวดหมู่ 6 หมวด + ร้าน mango (ไม่มีสินค้าตัวอย่าง)
backend/app/storage.py              จัดการไฟล์อัปโหลดบนดิสก์ (แปลง URL↔path, ลบไฟล์)
backend/app/config.py               ค่าตั้งค่าจาก environment variable + ตรวจความปลอดภัยตอน startup
backend/app/routers/
    auth.py        สมัคร/ล็อกอิน/ข้อมูลผู้ใช้
    categories.py  หมวดหมู่สินค้า
    uploads.py     อัปโหลดรูป/วิดีโอ
    products.py    สินค้า (อ่านได้ทุกคน, เขียนเฉพาะเจ้าของร้าน)
    shops.py       ร้านค้า
    cart.py        ตะกร้าสินค้า
    orders.py      คำสั่งซื้อ + เปลี่ยนสถานะ
    reviews.py     รีวิว

frontend/index.html                 หน้าแรก: ค้นหา + หมวดหมู่ + ตัวกรอง
frontend/pages/product-detail.html  รายละเอียดสินค้า + แกลเลอรีสื่อ + รีวิว
frontend/pages/shop.html            หน้าร้านค้า
frontend/pages/cart.html            ตะกร้าสินค้า (จัดกลุ่มตามร้าน)
frontend/pages/checkout.html        กรอกที่อยู่ + เลือกวิธีชำระเงิน
frontend/pages/orders.html          คำสั่งซื้อของฉัน + ติดตามสถานะ + เขียนรีวิว
frontend/pages/seller.html          แดชบอร์ดร้าน (สินค้า / คำสั่งซื้อ / ตั้งค่า)
frontend/pages/product-form.html    ฟอร์มลงขาย-แก้ไขสินค้า + อัปโหลดสื่อ
frontend/pages/login.html           สมัครสมาชิก / เข้าสู่ระบบ

docs/user-journey.md                User Journey ที่ใช้อ้างอิง
docs/er-diagram.md                  โครงสร้างตาราง + เหตุผลการออกแบบ + flow สถานะออเดอร์
docs/api-spec.md                    รายการ API endpoint ทั้งหมด
docs/deployment.md                  คู่มือ deploy ขึ้น Render/Railway ทีละขั้น
docs/presentation.docx              เอกสารนำเสนอ: โครงสไลด์ 11 แผ่น + สคริปต์พูด + คำถาม-คำตอบ
render.yaml                         Blueprint สร้างเว็บ+ฐานข้อมูลบน Render ในคลิกเดียว
```

## Edge Cases ที่ระบบจัดการ

| กรณี | ผลลัพธ์ |
|---|---|
| สินค้าหมด / ใกล้หมด (≤5) | ปิดปุ่มสั่งซื้อ / แจ้งเตือนให้รีบซื้อ |
| ค้นหาหรือกรองแล้วไม่พบ | แสดงข้อความแนะนำแทนหน้าว่าง |
| ซื้อสินค้าของร้านตัวเอง | บล็อกทั้งตอนใส่ตะกร้าและตอน checkout |
| **สองคนแย่งซื้อชิ้นสุดท้ายพร้อมกัน** | ล็อก row ด้วย `SELECT … FOR UPDATE` — stock ไม่มีทางติดลบ |
| stock ไม่พอตอน checkout | แจ้งชื่อสินค้าที่ไม่พอ และไม่สร้างออเดอร์ค้างไว้ครึ่งๆ |
| ร้านขึ้นราคาหลังลูกค้าสั่งไปแล้ว | ใบสั่งซื้อใช้ราคา snapshot ตอนสั่ง ไม่เปลี่ยนตาม |
| ยกเลิกคำสั่งซื้อ | คืน stock + หักยอดขายอัตโนมัติ |
| สินค้าถูกปิดขายแต่ค้างในตะกร้า | ข้ามตอน checkout ไม่ทำให้ทั้งออเดอร์ล้ม |
| ตะกร้ามีสินค้าหลายร้าน | แยกเป็นคนละคำสั่งซื้ออัตโนมัติ (แต่ละร้านส่งของแยกกัน) |
| รีวิวซ้ำ / รีวิวก่อนได้รับของ | ปฏิเสธ (1 รายการที่ซื้อ รีวิวได้ครั้งเดียว) |
| อัปโหลดไฟล์ผิดชนิด/ใหญ่เกิน | ปฏิเสธพร้อมบอกขนาดที่รับได้ |
| แก้/ลบสินค้าคนอื่น, ดูออเดอร์คนอื่น | 403 |
| ลบสินค้าที่เคยมีคนสั่งซื้อ | ปิดขายแทนลบจริง ประวัติคำสั่งซื้อยังครบ |
| เอารูป/วิดีโอออกจากสินค้า | ลบไฟล์บนดิสก์ให้ด้วย เว้นแต่มีสินค้าชิ้นอื่นใช้ไฟล์เดียวกันอยู่ |
| ใช้เครื่องร่วมกันแล้วออกจากระบบ | ล้าง cart token + backend ปฏิเสธการ claim ตะกร้าของบัญชีอื่น |

## Prompt ที่ใช้ (แยกตามสัปดาห์)

### สัปดาห์ 1 — Frontend scaffold
> สร้าง FastAPI backend ที่ serve static frontend ในตัวเดียว มี router `products.py` คืน mock data
> ตาม User Journey "อีคอมเมิร์ซ — Marketplace: ค้นหาและสั่งซื้อสินค้า" พร้อมหน้า HTML 3 หน้า
> (ค้นหา/รายการสินค้า, รายละเอียดสินค้า, ตะกร้าสินค้า) เรียก API ด้วย `fetch()` และรองรับ
> Edge Case: สินค้าหมด, สต็อกใกล้หมด, ค้นหาไม่พบ

### สัปดาห์ 2 — Database + Backend จริง
> จาก User Journey นี้ ช่วยออกแบบ Database Schema โดยใช้ SQLModel (Python) แยก entity Shop
> กับ Product ออกจากกัน (ความสัมพันธ์ one-to-many) เพราะ Pain Point ในเอกสารบอกว่าลูกค้า
> "ไม่รู้จะเชื่อร้านไหน" จากนั้นย้าย endpoint จาก mock data ไปอ่าน/เขียนจาก PostgreSQL จริง
> โดยคง response shape เดิมไว้ เพื่อไม่ต้องแก้ frontend ที่เขียนไว้ตั้งแต่สัปดาห์ 1

### สัปดาห์ 3 — เชื่อม frontend กับ backend จริง
> ย้ายตะกร้าสินค้าจาก localStorage ไปเป็นตาราง Cart/CartItem จริงใน PostgreSQL โดยที่ยังไม่มี
> ระบบล็อกอิน ให้ frontend สร้าง token เก็บใน localStorage แล้วส่งไปผูกกับตะกร้าใน DB
> เพิ่ม router `cart.py` ครบ CRUD แล้วแก้ frontend ให้เรียก API จริงแทน localStorage ทั้งหมด

### สัปดาห์ 4 — ระบบล็อกอิน + Edge Case
> เพิ่มระบบสมัคร/ล็อกอินด้วย JWT ตามมาตรฐาน OAuth2PasswordBearer ของ FastAPI (bcrypt เข้ารหัส
> รหัสผ่าน) แล้วเอา dependency `get_current_user` ไปผูกกับ endpoint ที่สร้าง/แก้ข้อมูล
> พร้อมแก้ Edge Case "สินค้าหมดสต็อกระหว่างลูกค้ากำลังเช็คเอาท์" ด้วย row-level lock
> (`SELECT ... FOR UPDATE`) ตอนเพิ่มสินค้าลงตะกร้า

### ปรับดีไซน์เว็บ (ระหว่างสัปดาห์ 4-5)
> ออกแบบหน้าเว็บใหม่ให้มีเอกลักษณ์ ไม่ใช้ template อีคอมเมิร์ซทั่วไป — เลือกแนวทาง
> "ท้องทะเลลึก" หัวเว็บกรมท่าเข้มมีพื้นผิวตัดกับเนื้อหาสีฟ้าอ่อน ใช้ฟอนต์ไทยที่มีคาแรกเตอร์
> (Taviraj + Chakra Petch) พร้อม hero section ตัดขอบทแยง, sticker badge, และ stagger animation
> — เปลี่ยนธีมทั้งเว็บได้จาก `:root` บล็อกเดียวใน `style.css` เพราะทุกสี (รวมเงา/แสงโปร่งใส)
> อ้างตัวแปร CSS ไม่มีค่าสีเขียนซ้ำกระจายในไฟล์

### สัปดาห์ 5 — Marketplace เต็มรูปแบบ (โพสขายได้ + ซื้อได้ + อัปโหลดสื่อ)
> ยกระดับเป็น marketplace ที่ผู้ใช้คนเดียวกันเป็นได้ทั้งผู้ซื้อและผู้ขาย:
> ผูก Shop กับ User (1 คน 1 ร้าน), เพิ่มตาราง Category / ProductMedia / Order / OrderItem / Review,
> ทำ endpoint อัปโหลดรูปและวิดีโอเก็บลง Docker volume, ระบบ checkout ที่แยก 1 ออเดอร์ต่อ 1 ร้าน
> พร้อมตัด stock แบบล็อก row, ชำระเงิน mock 3 ช่องทาง (ปลายทาง/โอน/บัตร), วงจรสถานะออเดอร์
> ครบตั้งแต่รอชำระจนถึงรีวิว, และระบบรีวิวที่ผูกกับ order_item_id เพื่อบังคับว่ารีวิวได้เฉพาะ
> สินค้าที่ซื้อจริงและได้รับแล้วเท่านั้น พร้อมหน้าเว็บใหม่: checkout, orders, seller dashboard,
> product form, หน้าร้าน — ใช้ design system เดิมที่มีอยู่แล้วต่อยอด ไม่รื้อใหม่


## Deploy URL
https://shopmarket-8dp6.onrender.com/
