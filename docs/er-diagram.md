# ER Diagram

Entity ทั้งหมดดึงมาจาก [user-journey.md](user-journey.md) โดยขยายจาก marketplace ฝั่งผู้ซื้ออย่างเดียว
เป็นระบบที่ผู้ใช้คนเดียวกัน **เป็นได้ทั้งผู้ซื้อและผู้ขาย**

```mermaid
erDiagram
    USER     ||--o| SHOP          : "เปิดร้าน (1 คน 1 ร้าน)"
    USER     ||--o{ ORDER         : "สั่งซื้อ"
    USER     ||--o{ REVIEW        : "เขียนรีวิว"
    USER     ||--o| CART          : "มีตะกร้า"
    SHOP     ||--o{ PRODUCT       : "ลงขาย"
    SHOP     ||--o{ ORDER         : "รับคำสั่งซื้อ"
    CATEGORY ||--o{ PRODUCT       : "จัดหมวดหมู่"
    PRODUCT  ||--o{ PRODUCT_MEDIA : "มีรูป/วิดีโอ"
    PRODUCT  ||--o{ CART_ITEM     : "ถูกใส่ตะกร้า"
    PRODUCT  ||--o{ ORDER_ITEM    : "ถูกสั่งซื้อ"
    CART     ||--o{ CART_ITEM     : "มีรายการ"
    ORDER    ||--o{ ORDER_ITEM    : "มีรายการ"
    ORDER_ITEM ||--o| REVIEW      : "รีวิวได้ 1 ครั้ง"

    USER {
        int id PK
        string email UK
        string name
        string hashed_password
        datetime created_at
    }

    SHOP {
        int id PK
        int owner_id FK "unique = 1 คน 1 ร้าน"
        string name
        string description
        float rating "คำนวณจาก REVIEW"
        int review_count
        bool is_verified
    }

    CATEGORY {
        int id PK
        string name
        string slug UK
        string icon
    }

    PRODUCT {
        int id PK
        int shop_id FK
        int category_id FK
        string name
        int price
        int original_price
        string description
        int stock
        bool free_shipping
        string image "emoji fallback"
        string cover_url "รูปแรก"
        float rating
        int review_count
        int sold
        bool is_active "ลบ = ปิดขาย"
    }

    PRODUCT_MEDIA {
        int id PK
        int product_id FK
        string url
        string media_type "image | video"
        int sort_order
    }

    CART {
        int id PK
        string token UK "ผูกกับ browser"
        int user_id FK "ผูกเมื่อล็อกอิน"
    }

    CART_ITEM {
        int id PK
        int cart_id FK
        int product_id FK
        int quantity
    }

    ORDER {
        int id PK
        string order_number UK
        int buyer_id FK
        int shop_id FK "1 order = 1 ร้าน"
        string status
        string payment_method
        int subtotal
        int shipping_fee
        int total
        string recipient_name
        string recipient_phone
        string address
        datetime created_at
    }

    ORDER_ITEM {
        int id PK
        int order_id FK
        int product_id FK
        string product_name "snapshot"
        int product_price "snapshot"
        int quantity
        int subtotal
    }

    REVIEW {
        int id PK
        int product_id FK
        int shop_id FK
        int user_id FK
        int order_item_id FK "unique"
        int rating "1-5"
        string comment
    }
```

## เหตุผลการออกแบบ

| การตัดสินใจ | เหตุผล |
|---|---|
| **`Shop.owner_id` unique** | 1 บัญชี = 1 ร้าน ทำให้สิทธิ์ชัดเจน: ใครแก้สินค้าได้บ้างเช็คจาก `product.shop.owner_id` |
| **`Shop.rating` แยกจาก `Product.rating`** | Pain Point ในเอกสารบอกว่า "ไม่รู้จะเชื่อร้านไหน" — คะแนนร้าน (ความน่าเชื่อถือ) กับคะแนนสินค้า (คุณภาพชิ้นนั้น) คนละความหมาย ทั้งคู่คำนวณสดจาก `REVIEW` ไม่ได้กรอกเอง |
| **1 Order = 1 ร้าน** | แต่ละร้านจัดส่งแยกกัน สถานะจึงต้องแยก — ตะกร้าที่มี 3 ร้านจะถูกแยกเป็น 3 ออเดอร์ตอน checkout (พฤติกรรมเดียวกับ Shopee) |
| **`OrderItem` เก็บ snapshot ชื่อ/ราคา** | ถ้าร้านขึ้นราคาหรือเปลี่ยนชื่อสินค้าทีหลัง ใบสั่งซื้อเก่าต้องไม่เปลี่ยนตาม |
| **`Product.is_active` (soft delete)** | ลบสินค้าจริงไม่ได้เพราะ `OrderItem` อ้างอิงอยู่ — ปิดขายแทน ประวัติการซื้อยังครบ |
| **`Review.order_item_id` unique** | บังคับว่ารีวิวได้เฉพาะสินค้าที่ซื้อจริง และ 1 รายการรีวิวได้ครั้งเดียว (กันรีวิวปลอม/รีวิวซ้ำ) |
| **`Cart.token` + `user_id` (nullable)** | guest ใส่ตะกร้าได้โดยไม่ต้องล็อกอิน พอล็อกอินแล้ว `/merge` จะผูกตะกร้าเข้าบัญชีและรวมกับตะกร้าเดิม |
| **`ProductMedia` แยกตาราง** | 1 สินค้ามีรูป/วิดีโอได้หลายชิ้นและเรียงลำดับได้ (`sort_order`) ส่วน `cover_url` เป็น denormalized ไว้ให้หน้า list โหลดเร็วโดยไม่ต้อง join |

## สถานะคำสั่งซื้อ

```
PENDING_PAYMENT ──(ชำระเงิน / COD ข้ามขั้นนี้)──> PAID ──(ร้านกดจัดส่ง)──> SHIPPED
       │                    │                                                 │
       │                    │                              (ผู้ซื้อกดรับของ) ──┘
       │                    │                                                 ↓
       └──(ยกเลิก + คืน stock)──┴────> CANCELLED            DELIVERED ──(รีวิวครบ)──> COMPLETED
```

- **COD** → สร้างออเดอร์เป็น `PAID` ทันที (ถือว่ายืนยันคำสั่งซื้อ จ่ายจริงตอนรับของ)
- **โอน/บัตร** → เริ่มที่ `PENDING_PAYMENT` ผู้ซื้อต้องกด "ชำระเงิน" ก่อน
- ยกเลิกได้ทั้งผู้ซื้อและร้าน ตราบใดที่ยังไม่ `SHIPPED` — ระบบคืน stock และหักยอด `sold` ให้อัตโนมัติ
