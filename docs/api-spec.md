# API Specification

Base URL (dev): `http://localhost:8000/api`

ทดสอบ endpoint ทั้งหมดได้ผ่าน Swagger UI ที่ `http://localhost:8000/docs`

**สถานะสัปดาห์ 4**: products/shops ต่อ PostgreSQL จริงตั้งแต่สัปดาห์ 2, ตะกร้าเป็น DB จริงตั้งแต่
สัปดาห์ 3, เพิ่มระบบสมัคร/ล็อกอิน (JWT) แล้วในสัปดาห์นี้ — endpoint ที่แก้ไข/สร้างข้อมูล (POST
products, POST shops) ต้องล็อกอินก่อนแล้ว ดูโครงสร้างตารางที่ [er-diagram.md](er-diagram.md)

### วิธีทดสอบผ่าน Swagger UI (`/docs`)
1. เรียก `POST /api/auth/register` สมัครสมาชิกก่อน 1 ครั้ง
2. กดปุ่ม **Authorize** (มุมขวาบนของหน้า `/docs`) กรอกอีเมล/รหัสผ่านที่สมัครไว้ (ช่อง username
   ใช้อีเมล) แล้วกด Authorize — Swagger จะแนบ Bearer token ให้อัตโนมัติทุก request หลังจากนี้
3. ทดสอบ `POST /api/products`, `POST /api/shops` ได้ตามปกติ (ก่อนหน้านี้ endpoint พวกนี้ต้อง 401
   ถ้ายังไม่ Authorize)

## Products

### GET /api/products
คืนรายการสินค้าทั้งหมด (join ชื่อร้านค้ามาเป็น `shop_name`)

**Query params**
| ชื่อ | ชนิด | บังคับ | คำอธิบาย |
|---|---|---|---|
| search | string | ไม่บังคับ | คำค้นหาชื่อสินค้า (ค้นแบบ substring, ไม่สนตัวพิมพ์เล็ก-ใหญ่) |

### GET /api/products/{product_id}
คืนข้อมูลสินค้ารายชิ้น — **404** ถ้าไม่พบ: `{"detail": "ไม่พบสินค้านี้"}`

### POST /api/products 🔒 ต้องล็อกอิน
สร้างสินค้าใหม่ — ต้องแนบ `Authorization: Bearer <token>` ไม่งั้นได้ **401**

**Request body**
```json
{
  "shop_id": 1,
  "name": "เมาส์ไร้สาย",
  "price": 199,
  "original_price": 299,
  "image": "🖱️",
  "category": "อุปกรณ์คอมพิวเตอร์",
  "description": "เมาส์ไร้สาย เชื่อมต่อผ่าน Bluetooth",
  "stock": 20,
  "free_shipping": true
}
```
**400** ถ้า `shop_id` ไม่มีอยู่จริง: `{"detail": "ไม่พบร้านค้าตาม shop_id ที่ระบุ"}`

## Shops

### GET /api/shops
คืนรายชื่อร้านค้าทั้งหมด

### POST /api/shops 🔒 ต้องล็อกอิน
สร้างร้านค้าใหม่ — ต้องแนบ `Authorization: Bearer <token>` ไม่งั้นได้ **401**
```json
{ "name": "ร้านใหม่", "rating": 0, "is_verified": false }
```

## Cart

ตะกร้าผูกกับ `token` ที่ frontend สร้างเองเก็บใน `localStorage` (คีย์ `shopmarket_cart_token`)
ยังไม่ผูกกับ `user_id` อัตโนมัติตอนล็อกอิน (รอสัปดาห์ถัดไปทำ merge logic) — คนละเบราว์เซอร์ =
คนละตะกร้า ไม่ว่าจะล็อกอินด้วยบัญชีเดียวกันหรือไม่

### GET /api/cart/{token}
คืนตะกร้าตาม token พร้อมรายการสินค้า+ยอดรวม — ถ้ายังไม่เคยเพิ่มสินค้าเลยจะได้ตะกร้าว่าง (ไม่ error)
```json
{ "token": "abc123", "items": [], "total": 0 }
```

### POST /api/cart/{token}/items
เพิ่มสินค้าลงตะกร้า (ถ้ามีอยู่แล้วจะบวกจำนวนเพิ่ม ไม่เกิน stock คงเหลือ)
```json
{ "product_id": 1, "quantity": 2 }
```
**400** ถ้าไม่พบสินค้า: `{"detail": "ไม่พบสินค้านี้"}`

### PATCH /api/cart/{token}/items/{product_id}
ปรับจำนวนสินค้าในตะกร้า (ตั้งเป็น 0 หรือน้อยกว่า = ลบออกจากตะกร้า)
```json
{ "quantity": 3 }
```
**404** ถ้าไม่พบตะกร้า/สินค้าในตะกร้า

### DELETE /api/cart/{token}/items/{product_id}
ลบสินค้าออกจากตะกร้า

## Auth

### POST /api/auth/register
สมัครสมาชิกใหม่
```json
{ "email": "a@example.com", "password": "secret123", "name": "คุณเอ" }
```
**400** ถ้าอีเมลซ้ำ: `{"detail": "อีเมลนี้ถูกใช้สมัครไปแล้ว"}`

### POST /api/auth/login
ล็อกอิน — ส่งเป็น form (ไม่ใช่ JSON) ตามมาตรฐาน OAuth2: field `username` (ใส่อีเมล) + `password`
```
username=a@example.com&password=secret123
```
คืน `{ "access_token": "...", "token_type": "bearer" }` — **401** ถ้าอีเมล/รหัสผ่านผิด

### GET /api/auth/me 🔒 ต้องล็อกอิน
คืนข้อมูลผู้ใช้ปัจจุบันจาก token — **401** ถ้า token ไม่มี/ผิด/หมดอายุ

---

## แผนสัปดาห์ 5 (ยังไม่ทำ)
- ผูก Cart กับ `user_id` อัตโนมัติตอนล็อกอิน (claim ตะกร้า guest เดิม)
- `POST /api/orders`, `GET /api/orders/{id}` — สร้าง/ติดตามคำสั่งซื้อจากตะกร้า (checkout จริง)
- Deploy ขึ้น Render/Railway
