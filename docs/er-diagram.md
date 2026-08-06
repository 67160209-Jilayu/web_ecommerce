# ER Diagram

ดึง Entity หลักจากตาราง "ขั้นตอน" ใน [user-journey.md](user-journey.md): ลูกค้าเปรียบเทียบราคา/รีวิว
**หลายร้าน** ก่อนตัดสินใจซื้อ และ Pain Point ที่ว่า "ไม่รู้จะเชื่อร้านไหน" — จึงแยก **ร้านค้า (Shop)**
ออกมาเป็น entity ของตัวเอง (สัปดาห์ 2) และเพิ่ม **ตะกร้าสินค้า (Cart/CartItem)** จริงในสัปดาห์ 3
แทนที่ localStorage เดิม

```mermaid
erDiagram
    SHOP ||--o{ PRODUCT : "มีสินค้า"
    PRODUCT ||--o{ CART_ITEM : "ถูกใส่ตะกร้า"
    CART ||--o{ CART_ITEM : "มีรายการ"

    SHOP {
        int id PK
        string name
        float rating
        bool is_verified
    }

    PRODUCT {
        int id PK
        int shop_id FK
        string name
        int price
        int original_price
        string image
        string category
        string description
        float rating
        int sold
        int stock
        bool free_shipping
    }

    CART {
        int id PK
        string token "ผูกกับ browser ผ่าน localStorage"
    }

    CART_ITEM {
        int id PK
        int cart_id FK
        int product_id FK
        int quantity
    }
```

## เหตุผลการออกแบบ
- **Shop 1 — * Product** (one-to-many): ร้านค้าหนึ่งร้านขายสินค้าได้หลายชิ้น ตรงกับที่ journey แสดง
  `shop_name` กำกับทุกสินค้าในหน้ารายการ/รายละเอียด
- `Shop.rating` และ `Shop.is_verified` แยกจาก `Product.rating` เพราะคนละความหมาย: รีวิวร้านค้า
  (ความน่าเชื่อถือ) กับรีวิวสินค้าชิ้นนั้นๆ (คุณภาพสินค้า) — รองรับ Pain Point "ไม่รู้จะเชื่อร้านไหน"
- **Cart 1 — * CartItem** (one-to-many): 1 ตะกร้ามีได้หลายรายการสินค้า
- `Cart.token` แทน `user_id` ชั่วคราว เพราะยังไม่มีระบบล็อกอิน (สัปดาห์ 4) — browser สร้าง token
  เก็บไว้ใน `localStorage` เอง แล้วส่งไปผูกกับตะกร้าใน DB ทุกครั้งที่เรียก API
- ยังไม่มีตาราง Order ในสัปดาห์นี้ เพราะยังไม่เปิดขั้นตอนชำระเงินจริง (รอสัปดาห์ 4-5)

## Endpoint ที่ทดสอบผ่าน Swagger UI แล้ว (`/docs`)
- `GET /api/products` — คืนสินค้าทั้งหมดจาก DB จริง (join ชื่อร้านมาด้วย)
- `GET /api/products/{id}` — คืนสินค้ารายชิ้น
- `POST /api/products` — สร้างสินค้าใหม่ ผูกกับ `shop_id` ที่มีอยู่จริง
- `GET /api/shops` — คืนรายชื่อร้านค้าทั้งหมด
- `POST /api/shops` — สร้างร้านค้าใหม่
- `GET /api/cart/{token}` — คืนตะกร้าตาม token (ตะกร้าว่างถ้ายังไม่เคยเพิ่มสินค้า)
- `POST /api/cart/{token}/items` — เพิ่มสินค้าลงตะกร้า
- `PATCH /api/cart/{token}/items/{product_id}` — ปรับจำนวน
- `DELETE /api/cart/{token}/items/{product_id}` — ลบออกจากตะกร้า
