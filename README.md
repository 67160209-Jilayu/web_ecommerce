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

> **อัปเกรด DB เก่า:** ไม่ต้อง `docker compose down -v` อีกแล้ว — ตอน startup ระบบเติมคอลัมน์ใหม่ (`ALTER TABLE … ADD COLUMN IF NOT EXISTS`)
> สร้างตาราง/ดัชนีใหม่ และเติมข้อมูลตั้งต้น (ประวัติราคา, `price_at_add`) ให้เอง ทำซ้ำได้ปลอดภัย
> (ยังไม่มีระบบ migration เต็มรูปแบบ — การเปลี่ยนชนิด/ลบคอลัมน์ยังต้องทำเอง)

### รันในเครื่องโดยไม่ใช้ Docker (SQLite)

ต้องมี Python 3.11+ (ทดสอบกับ 3.13) — ไม่ต้องมี PostgreSQL

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt     # (Linux/macOS: .venv/bin/python)
$env:PYTHONUTF8 = "1"                                         # Windows: ข้อความตอน startup เป็นภาษาไทย
$env:DATABASE_URL = "sqlite:///./shopmarket-dev.db"           # ไฟล์ DB อยู่ใน backend/ (ลบไฟล์ = รีเซ็ต)
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

เปิด http://localhost:8000 · path ของ `frontend/` และ `uploads/` อ้างอิงจากตำแหน่งโค้ดแล้ว (ไม่ต้องรันจากโฟลเดอร์ใดโดยเฉพาะ)
ข้อจำกัดของ SQLite: ไม่มี `SELECT … FOR UPDATE` จึงทดสอบการแย่งซื้อชิ้นสุดท้ายพร้อมกันไม่ได้ — ใช้ PostgreSQL ตอนใช้งานจริง

### ตัวแปรสภาพแวดล้อม (Environment variables)

ค่าลับ (key/password) ตั้งผ่าน environment เท่านั้น **ห้ามเขียนลงโค้ดหรือ commit**

| ตัวแปร | ค่าเริ่มต้น | ใช้ทำอะไร |
|---|---|---|
| `DATABASE_URL` | `postgresql://appuser:apppassword@db:5432/appdb` | ฐานข้อมูล (`sqlite:///./x.db` สำหรับรันในเครื่อง) |
| `APP_ENV` | `development` | `production` = ตรวจ `SECRET_KEY` เข้มงวด |
| `SECRET_KEY` | ค่า dev | ลงนาม JWT — production ต้องสุ่มยาว ≥ 32 ตัวอักษร |
| `CLOUDINARY_URL` | – | ที่เก็บรูป/วิดีโอบนคลาวด์ (ไม่ตั้ง = เก็บลงดิสก์ `UPLOAD_DIR`) |
| `LLM_PROVIDER` | `auto` | `auto` (มี `GEMINI_API_KEY` → gemini, ไม่มี → ไม่ใช้โมเดล) · `gemini` · `fake` (ทดสอบ/เดโม ไม่ต่อเน็ต) · `none` |
| `GEMINI_API_KEY` | – | key ของ Gemini (ค่าลับ — ตั้งใน environment ของเครื่อง/Render เท่านั้น) |
| `LLM_MODEL` | `gemini-2.5-flash-lite` | ชื่อโมเดลแชท/สรุป (เปลี่ยนได้โดยไม่แก้โค้ด เพราะรุ่นถูกปิดบ่อย) |
| `LLM_EMBED_MODEL` | `gemini-embedding-001` | โมเดลทำเวกเตอร์สำหรับค้นหาตามความหมาย |
| `CHAT_ENABLED` / `CHAT_ROLLOUT_PERCENT` | `true` / `100` | สวิตช์แชท + % ผู้ใช้ที่เปิดให้ (ขึ้นจริงแนะนำเริ่ม 5) |
| `SEMANTIC_SEARCH` | `false` | เปิดค้นหาตามความหมาย |
| `PRICE_GRACE_ENABLED` / `PRICE_GRACE_START` / `PRICE_GRACE_DAYS` | `true` / `2026-10-03` / `30` | ช่วงผ่อนผันกฎราคาก่อนลด |
| `PRICE_REF_MIN_DAYS` / `PRICE_RAISE_PERCENT` | `7` / `15` | เกณฑ์ราคาก่อนลด / ขึ้นราคาก่อนลดกี่ % ถึงซ่อน % ส่วนลด |
| `CART_NOTICE_MIN_PERCENT` / `CART_NOTICE_MIN_BAHT` | `3` / `20` | เกณฑ์แจ้งราคาลดในตะกร้า (อย่างใดอย่างหนึ่ง) |
| `REVIEW_SUMMARY_MIN_REVIEWS` | `3` | จำนวน **คนรีวิว** ขั้นต่ำก่อนแสดงสรุปรีวิว |
| `FUZZY_MATCH_THRESHOLD` | `0.6` | เกณฑ์ "อาจเป็นรุ่นเดียวกัน" |

ไม่มี `GEMINI_API_KEY` ก็ใช้งานได้ครบ: ฟีเจอร์ที่ใช้โมเดลจะถอยกลับอัตโนมัติ (สรุปเปรียบเทียบแบบกฎ, แชทเป็นโหมดปุ่มเลือก, ไม่มีสรุปรีวิว/ค้นหาตามความหมาย)

### สวิตช์แชท / ค้นหาตามความหมาย (เปลี่ยนได้โดยไม่ต้อง deploy)

```bash
cd backend
python -m app.settings get
python -m app.settings set chat_enabled false          # ปิดแชททันที
python -m app.settings set chat_rollout_percent 5      # เปิดให้ 5% ของผู้ใช้
python -m app.settings set semantic_search true
python -m app.settings unset chat_enabled              # กลับไปใช้ค่าจาก env
```

### งานตามเวลา (รันด้วย cron / Task Scheduler / Render Cron Job)

ทุกงานรันซ้ำได้ปลอดภัย และ **รันอัตโนมัติตอน startup** ด้วยอยู่แล้ว (ยกเว้นข้อ 3–5):

1. `python -m app.pricing` — กลางคืน (แนะนำ 02:00): เติมประวัติราคาที่ขาด, คำนวณราคาก่อนลดทุกสินค้า, ซิงก์แจ้งเตือนในตะกร้า, ลบ log แชทเกิน 30 วัน
2. `python -m app.chat` — ลบ log/cache แชทที่หมดอายุ (อยู่ในข้อ 1 แล้ว)
3. `python -m app.spec_suggest` — ให้โมเดลเสนอสเปกจากคำอธิบายสินค้า (ผู้ขายต้องกดยืนยันเอง ไม่บันทึกอัตโนมัติ)
4. `python -m app.review_summary` — สร้าง/อัปเดตสรุปรีวิว
5. `python -m app.semantic` — สร้างเวกเตอร์ค้นหาตามความหมายให้สินค้าทั้งหมด (ก่อนเปิด `SEMANTIC_SEARCH`)

### รันชุดทดสอบ

```powershell
cd backend
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest tests -q
```

ทดสอบบน SQLite ชั่วคราว ไม่ต่อเน็ต และบังคับ `LLM_PROVIDER=none` (เปิด `fake` เฉพาะเทสต์ที่ต้องการ) จึงไม่เรียก Gemini จริงแม้มี key ในเครื่อง ·
ชุดทดสอบแชท 200 คำถาม (ปกติ 150 + โจมตี 50): `python -m tests.eval.run_eval [--adversarial]` ·
กับโมเดลจริง: `python -m tests.eval.run_eval --real` (ทำงานเฉพาะเมื่อมี `GEMINI_API_KEY` ใน environment อยู่แล้ว)

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

## ฟีเจอร์เพิ่มเติม (เฟส 1–4)

**ราคาที่เชื่อถือได้**
- ระบบจดประวัติราคา/สต็อกเบื้องหลังทุกครั้งที่เปลี่ยน (ไม่แสดงกราฟต่อผู้ซื้อ) ผู้ขายตั้งราคาขีดฆ่าเองไม่ได้ —
  "ราคาก่อนลด" = ราคาต่ำสุดใน 30 วันก่อนเริ่มลด (ต้องมีราคาที่ใช้จริง ≥ 7 วัน) · ขึ้นราคา ≥ 15% ภายใน 14 วันก่อนลด → ซ่อน % ส่วนลด และบอกผู้ขายพร้อมเหตุผล
  (ช่วง 30 วันแรกแค่เตือน) · แดชบอร์ดราคาสำหรับผู้ขาย: `GET /api/seller/price-status`
- แจ้งเตือนราคาลดในตะกร้า (เฉพาะผู้ใช้ที่ล็อกอิน): แถบบนหน้าตะกร้า + จุดที่ไอคอนตะกร้า ไม่มี push/อีเมล/LINE

**เปรียบเทียบสินค้า** — หน้า `pages/compare.html?ids=1,2,3` (แชร์ลิงก์ได้)
- แม่แบบสเปกต่อหมวด (หน่วยล็อก เลือกจากตัวเลือก) · ป้าย "ข้อมูลครบ" · ระบบเสนอสเปกจากคำอธิบายให้ผู้ขายกดยืนยัน
- ซ่อนสเปกที่เหมือนกัน · ค่าที่ดีกว่าไฮไลต์ · ค่าส่ง/ระยะเวลา/ราคารวมตามจังหวัดผู้ซื้อ · สรุป 1 บรรทัดที่ตัวเลขตรงกับตารางเสมอ
- "ร้านอื่นที่ขายรุ่นนี้" (บาร์โค้ด/แบรนด์+รหัสรุ่นตรงกัน) แยกจาก "อาจเป็นรุ่นเดียวกัน" (จับคู่โดยประมาณ — ตัดรุ่นย่อยต่างกันและสินค้าเลียนแบบออก)
- ผู้ขายตั้งค่าส่งของร้านได้ (เรทเดียว + เรทเฉพาะภาค + ส่งฟรีเมื่อครบ) — ใช้ตัวเดียวกันทั้งหน้าเทียบ ตะกร้า และ checkout

**ผู้ช่วยช้อป (แชท)** — ตอบเฉพาะการหา/เทียบสินค้าจากข้อมูลจริงในระบบ
- ไม่ต่อรองราคา ไม่สัญญา/รับประกันแทนร้าน ไม่บอกแนวโน้มราคา ราคาทุกตัวต้องตรงกับผลค้นจากฐานข้อมูล ไม่ผ่านการตรวจ → แสดงเฉพาะการ์ดสินค้า
- จำกัดการใช้ + cache + log ที่ตัดข้อมูลส่วนตัว 30 วัน · ใช้โมเดลไม่ได้ → โหมดปุ่มเลือกทีละขั้น (หมวด → งบ → การใช้งาน)
- เปิด/ปิดและค่อยๆ เปิดให้ผู้ใช้ได้โดยไม่ต้อง deploy (ดู "สวิตช์แชท")

**เฟสต่อยอด**: สรุป "ลูกค้าชม/ลูกค้าติ" จากรีวิวจริง (แนบข้อความที่อ้างถึง ต้องมีผู้รีวิว ≥ 3 คน) · ค้นหาตามความหมาย
("ของขวัญให้แม่") แบบผสมกับค้นหาด้วยคำ ปิดไว้เป็นค่าเริ่มต้น และถอยกลับเป็นค้นหาปกติเมื่อมีปัญหาเสมอ

รายละเอียด API ทั้งหมด: [docs/api-spec.md](docs/api-spec.md)

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
backend/app/pricing.py              ประวัติราคา, ราคาก่อนลดที่ระบบคำนวณ, กฎขึ้นราคาก่อนลด, แจ้งเตือนราคาลดในตะกร้า
backend/app/specs.py                แม่แบบสเปกต่อหมวด + ตรวจค่าที่ผู้ขายกรอก
backend/app/shipping.py             ค่าส่งต่อร้าน/ภาค, 77 จังหวัด, หาจังหวัดผู้ซื้อ
backend/app/compare.py              ตารางเปรียบเทียบ, ป้าย, สรุป, ร้านอื่นที่ขายรุ่นนี้
backend/app/matching.py             "อาจเป็นรุ่นเดียวกัน" (จับคู่โดยประมาณ)
backend/app/llm.py                  ชั้นเรียกโมเดล (gemini / fake / none) + embed
backend/app/chat.py, chat_guard.py  ผู้ช่วยช้อป + ด่านกรอง 4 ชั้น
backend/app/review_summary.py       สรุปรีวิวจากรีวิวจริง
backend/app/semantic.py             ค้นหาตามความหมาย (เวกเตอร์ใน DB)
backend/app/spec_suggest.py         ระบบเสนอสเปกจากคำอธิบาย (batch)
backend/app/settings.py             สวิตช์ที่เปลี่ยนได้โดยไม่ต้อง deploy (app_setting)
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
