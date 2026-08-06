# API Specification

Base URL (dev): `http://localhost:8000/api`

ทดสอบ endpoint ทั้งหมดได้ผ่าน Swagger UI ที่ `http://localhost:8000/docs`

**สถานะสัปดาห์ 2**: ทุก endpoint อ่าน/เขียนจาก PostgreSQL จริงแล้ว (เลิกใช้ mock data ของสัปดาห์ 1)
ดูโครงสร้างตารางที่ [er-diagram.md](er-diagram.md)

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

---

## แผนสัปดาห์ 3-4 (ยังไม่ทำ)
- `POST /api/orders`, `GET /api/orders/{id}` — สร้าง/ติดตามคำสั่งซื้อ (ย้ายตะกร้าจาก localStorage)
- ระบบล็อกอิน/สิทธิ์ผู้ใช้ ผูกกับ endpoint ที่แก้ไข/ลบข้อมูล
