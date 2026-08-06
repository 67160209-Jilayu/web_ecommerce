# API Specification

Base URL (dev): `http://localhost:8000/api`

ทดสอบ endpoint ทั้งหมดได้ผ่าน Swagger UI ที่ `http://localhost:8000/docs`

**สถานะสัปดาห์ 3**: products/shops ต่อ PostgreSQL จริงตั้งแต่สัปดาห์ 2, ตะกร้าสินค้าย้ายจาก
localStorage มาเป็น DB จริงแล้วในสัปดาห์นี้ ดูโครงสร้างตารางที่ [er-diagram.md](er-diagram.md)

## Products

### GET /api/products
คืนรายการสินค้าทั้งหมด (join ชื่อร้านค้ามาเป็น `shop_name`)

**Query params**
| ชื่อ | ชนิด | บังคับ | คำอธิบาย |
|---|---|---|---|
| search | string | ไม่บังคับ | คำค้นหาชื่อสินค้า (ค้นแบบ substring, ไม่สนตัวพิมพ์เล็ก-ใหญ่) |

### GET /api/products/{product_id}
คืนข้อมูลสินค้ารายชิ้น — **404** ถ้าไม่พบ: `{"detail": "ไม่พบสินค้านี้"}`

### POST /api/products
สร้างสินค้าใหม่ (ยังไม่มีระบบสิทธิ์ผู้ใช้ รอสัปดาห์ 4)

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

### POST /api/shops
สร้างร้านค้าใหม่
```json
{ "name": "ร้านใหม่", "rating": 0, "is_verified": false }
```

## Cart

ตะกร้าผูกกับ `token` ที่ frontend สร้างเองเก็บใน `localStorage` (คีย์ `shopmarket_cart_token`)
ยังไม่ผูกกับผู้ใช้จริงเพราะไม่มีระบบล็อกอิน (รอสัปดาห์ 4) — คนละเบราว์เซอร์ = คนละตะกร้า

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

---

## แผนสัปดาห์ 4-5 (ยังไม่ทำ)
- ระบบล็อกอิน/สิทธิ์ผู้ใช้ — ผูกตะกร้ากับ user_id แทน token เมื่อล็อกอินแล้ว
- `POST /api/orders`, `GET /api/orders/{id}` — สร้าง/ติดตามคำสั่งซื้อจากตะกร้า (checkout จริง)
