# API Specification

Base URL (dev): `http://localhost:8000/api` · ทดสอบทุก endpoint ได้ที่ Swagger UI `http://localhost:8000/docs`

🔒 = ต้องแนบ `Authorization: Bearer <token>` (ไม่มี/หมดอายุ → **401**)
ดูโครงสร้างตารางที่ [er-diagram.md](er-diagram.md)

### วิธีทดสอบผ่าน Swagger UI
1. `POST /api/auth/register` สมัครสมาชิก
2. กด **Authorize** มุมขวาบน กรอกอีเมล (ช่อง username) + รหัสผ่าน
3. เรียก endpoint ที่มี 🔒 ได้ตามปกติ

> บัญชีตัวอย่างที่ seed ไว้: `mango@shopmarket.test` รหัสผ่าน `mango1234` (ร้าน mango, ยังไม่มีสินค้า)

---

## Auth

| Method | Path | คำอธิบาย |
|---|---|---|
| POST | `/auth/register` | สมัครสมาชิก — **400** ถ้าอีเมลซ้ำ |
| POST | `/auth/login` | ล็อกอิน (ส่งเป็น form: `username`=อีเมล, `password`) คืน JWT — **401** ถ้าผิด |
| GET | `/auth/me` 🔒 | ข้อมูลผู้ใช้ปัจจุบัน |

## Categories

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/categories` | หมวดหมู่ทั้งหมด (seed ไว้ 6 หมวด) |

## Uploads

### POST `/uploads` 🔒
อัปโหลดรูป/วิดีโอ 1 ไฟล์ (multipart, field ชื่อ `file`) → `{ "url": "/uploads/xxx.jpg", "media_type": "image" }`

- รูป: `jpg/png/webp/gif` ≤ **5MB** · วิดีโอ: `mp4/webm/mov` ≤ **50MB**
- ตรวจจาก content-type จริง ไม่เชื่อนามสกุลไฟล์ · ตั้งชื่อไฟล์ใหม่ด้วย UUID (กัน path traversal)
- **400** ถ้าชนิดไฟล์ไม่รองรับหรือใหญ่เกินกำหนด

## Shops

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/shops` | รายชื่อร้านทั้งหมด |
| GET | `/shops/me` 🔒 | ร้านของฉัน — **404** ถ้ายังไม่เปิดร้าน |
| POST | `/shops` 🔒 | เปิดร้าน — **400** ถ้ามีร้านแล้ว (1 บัญชี 1 ร้าน) |
| PATCH | `/shops/me` 🔒 | แก้ชื่อ/คำโปรยร้าน |
| GET | `/shops/{id}` | หน้าร้าน public |
| GET | `/shops/{id}/products` | สินค้าที่เปิดขายในร้านนี้ |

## Products

### GET `/products`
คืนสินค้าที่ `is_active = true` พร้อมตัวกรอง

| Query | ชนิด | คำอธิบาย |
|---|---|---|
| `search` | string | ค้นจากชื่อ + คำอธิบาย (ไม่สนตัวพิมพ์เล็ก-ใหญ่) |
| `category_id` | int | กรองตามหมวดหมู่ |
| `min_price` / `max_price` | int | ช่วงราคา |
| `sort` | string | `latest`(ค่าเริ่มต้น) `price_asc` `price_desc` `popular` `rating` |

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/products/me` 🔒 | สินค้าทั้งหมดในร้านฉัน (รวมที่ปิดขาย) |
| GET | `/products/{id}` | รายละเอียด + `media[]` — **404** ถ้าไม่พบ |
| GET | `/products/{id}/reviews` | รีวิวของสินค้าชิ้นนี้ |
| POST | `/products` 🔒 | ลงขาย — **400** ถ้ายังไม่เปิดร้าน / ราคา ≤ 0 |
| PATCH | `/products/{id}` 🔒 | แก้ไข — **403** ถ้าไม่ใช่ร้านตัวเอง |
| DELETE | `/products/{id}` 🔒 | ปิดขาย (soft delete) — **403** ถ้าไม่ใช่ร้านตัวเอง |

**ตัวอย่าง body ของ POST `/products`**
```json
{
  "name": "หูฟังบลูทูธ", "price": 890, "original_price": 1490,
  "category_id": 4, "description": "เสียงดี ตัดเสียงรบกวน",
  "stock": 20, "free_shipping": true, "image": "🎧",
  "media": [
    { "url": "/uploads/abc123.jpg", "media_type": "image" },
    { "url": "/uploads/def456.mp4", "media_type": "video" }
  ]
}
```

## Cart

ตะกร้าผูกกับ `token` ที่ frontend สร้างเก็บใน localStorage — guest ใช้ได้โดยไม่ต้องล็อกอิน

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/cart/{token}` | คืนตะกร้า (ว่างถ้ายังไม่เคยใช้ ไม่ error) |
| POST | `/cart/{token}/items` | เพิ่มสินค้า — **400** ถ้าสินค้าหมด/ไม่พบ/เป็นของร้านตัวเอง |
| PATCH | `/cart/{token}/items/{product_id}` | ปรับจำนวน (0 = ลบออก) |
| DELETE | `/cart/{token}/items/{product_id}` | ลบออกจากตะกร้า |
| POST | `/cart/{token}/merge` 🔒 | ผูกตะกร้า guest เข้าบัญชีตอนล็อกอิน (รวมกับตะกร้าเดิม) |

## Orders

### POST `/orders/checkout?token={cart_token}` 🔒
แปลงตะกร้าเป็นคำสั่งซื้อ — **แยก 1 ออเดอร์ต่อ 1 ร้าน** คืนเป็น array

```json
{
  "recipient_name": "สมชาย ใจดี", "recipient_phone": "0812345678",
  "address": "123 ถ.สุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพฯ 10110",
  "note": "ฝากไว้ที่นิติบุคคล", "payment_method": "COD"
}
```
- `payment_method`: `COD` | `BANK_TRANSFER` | `CARD`
- ค่าส่ง ฿40/ร้าน · ฟรีเมื่อยอดต่อร้าน ≥ ฿500 หรือสินค้าทุกชิ้นตั้งค่า `free_shipping`
- ตัด stock ภายใน transaction เดียว (ล็อก row ด้วย `SELECT … FOR UPDATE`)
- **400** ถ้า: ตะกร้าว่าง / stock ไม่พอ (ระบุชื่อสินค้า) / มีสินค้าของร้านตัวเอง

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/orders/me` 🔒 | คำสั่งซื้อที่ฉันเป็นผู้ซื้อ |
| GET | `/orders/selling` 🔒 | คำสั่งซื้อเข้าร้านฉัน (ผู้ขาย) |
| GET | `/orders/{id}` 🔒 | รายละเอียด — **403** ถ้าไม่ใช่ผู้ซื้อหรือเจ้าของร้าน |
| POST | `/orders/{id}/pay` 🔒 | ผู้ซื้อยืนยันชำระเงิน (mock) — ต้องเป็น `PENDING_PAYMENT` |
| POST | `/orders/{id}/ship` 🔒 | ร้านกดจัดส่ง — ต้องเป็น `PAID` |
| POST | `/orders/{id}/receive` 🔒 | ผู้ซื้อกดรับของ — ต้องเป็น `SHIPPED` |
| POST | `/orders/{id}/cancel` 🔒 | ยกเลิก + คืน stock — ทำได้ทั้ง 2 ฝ่าย ตราบใดที่ยังไม่ `SHIPPED` |

## Reviews

### POST `/reviews` 🔒
```json
{ "order_item_id": 12, "rating": 5, "comment": "ของตรงปก ส่งไวมาก" }
```
- **403** ถ้าไม่ใช่ผู้สั่งซื้อ · **400** ถ้ายังไม่กดรับของ / รีวิวรายการนี้ไปแล้ว / คะแนนไม่อยู่ในช่วง 1-5
- เมื่อสำเร็จ ระบบคำนวณ `rating` ของสินค้าและร้านใหม่ทันที และถ้ารีวิวครบทุกรายการในออเดอร์
  สถานะออเดอร์จะเปลี่ยนเป็น `COMPLETED`

---

## สรุป Edge Case ที่ระบบจัดการ

| กรณี | ผลลัพธ์ |
|---|---|
| ซื้อสินค้าของร้านตัวเอง | 400 (บล็อกทั้งตอนใส่ตะกร้าและตอน checkout) |
| stock ไม่พอตอน checkout | 400 ระบุชื่อสินค้า + ไม่สร้างออเดอร์ใดเลย |
| สองคนแย่งซื้อสินค้าชิ้นสุดท้ายพร้อมกัน | ล็อก row ด้วย `FOR UPDATE` — คนหลังได้ 400 ไม่ติดลบ |
| ร้านขึ้นราคาหลังลูกค้าสั่ง | ใบสั่งซื้อใช้ราคา snapshot เดิม |
| ยกเลิกออเดอร์ | คืน stock + หักยอด `sold` อัตโนมัติ |
| สินค้าถูกปิดขายแต่ค้างในตะกร้า | ข้ามตอน checkout ไม่ทำให้ทั้งออเดอร์ล้ม |
| รีวิวซ้ำ / รีวิวก่อนได้ของ | 400 (unique `order_item_id`) |
| อัปโหลดไฟล์ผิดชนิด/ใหญ่เกิน | 400 พร้อมบอกขนาดที่รับได้ |
| แก้/ลบสินค้าคนอื่น, ดูออเดอร์คนอื่น | 403 |
| เปิดร้านซ้ำ / ลงขายทั้งที่ยังไม่มีร้าน | 400 พร้อมชี้ทางแก้ |
