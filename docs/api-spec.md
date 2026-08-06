# API Specification (Week 1)

Base URL (dev): `http://localhost:8000/api`

ทดสอบ endpoint ทั้งหมดได้ผ่าน Swagger UI ที่ `http://localhost:8000/docs`

## GET /api/products
คืนรายการสินค้าทั้งหมด (mock data)

**Query params**
| ชื่อ | ชนิด | บังคับ | คำอธิบาย |
|---|---|---|---|
| search | string | ไม่บังคับ | คำค้นหาชื่อสินค้า (ค้นแบบ substring, ไม่สนตัวพิมพ์เล็ก-ใหญ่) |

**ตัวอย่าง response**
```json
[
  {
    "id": 1,
    "name": "หมอนรองคอเมมโมรี่โฟม รุ่นเดินทาง",
    "price": 199,
    "original_price": 350,
    "image": "🧸",
    "shop_name": "HomeComfort Shop",
    "rating": 4.8,
    "sold": 2431,
    "stock": 15,
    "free_shipping": true,
    "category": "ของใช้ในบ้าน",
    "description": "..."
  }
]
```

## GET /api/products/{product_id}
คืนข้อมูลสินค้ารายชิ้น

**Response 404** ถ้าไม่พบสินค้า: `{"detail": "ไม่พบสินค้านี้"}`

---

## แผนสัปดาห์ 2 (ยังไม่ทำ)
- `POST /api/products` — เพิ่มสินค้า (ต้อง auth)
- เชื่อม endpoint ทั้งหมดกับ PostgreSQL ผ่าน SQLModel แทน mock data
- `POST /api/orders`, `GET /api/orders/{id}` — สร้าง/ติดตามคำสั่งซื้อ
