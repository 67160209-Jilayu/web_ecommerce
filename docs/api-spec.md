# API Specification

Base URL (dev): `http://localhost:8000/api` · ทดสอบทุก endpoint ได้ที่ Swagger UI `http://localhost:8000/docs`

🔒 = ต้องแนบ `Authorization: Bearer <token>` (ไม่มี/หมดอายุ → **401**)
ดูโครงสร้างตารางที่ [er-diagram.md](er-diagram.md)

> เอกสารนี้ครอบคลุม endpoint ทุกเฟส (ราคา/แจ้งเตือนในตะกร้า, เปรียบเทียบ, แชท, สรุปรีวิว, ค้นหาตามความหมาย) —
> หัวข้อ "เพิ่มในเฟส 1–4" ด้านล่างสุดคือส่วนที่เพิ่มจากเดิม ดูตัวอย่าง schema จริงได้ที่ `/docs` (Swagger)

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
| GET | `/categories/{id}/attributes` | แม่แบบสเปกของหมวด (`key, name_th, unit, data_type, options, group_name, better, required, sort, badge_label`) |

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
  "name": "หูฟังบลูทูธ", "price": 890, "brand": "SoundPods", "model_code": "SP-PRO",
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
- ค่าส่งคิดต่อร้านจาก engine เดียวกับหน้าเทียบ/ใบเสนอค่าส่ง (ดูเฟส 2) — ค่าเริ่มต้น ฿40/ร้าน ฟรีเมื่อยอดต่อร้าน ≥ ฿500 หรือสินค้าทุกชิ้นตั้งค่า `free_shipping`
- body เพิ่ม `province` ได้ (ไม่ส่ง = เดาจากที่อยู่ ถ้าไม่เจอใช้เรทเดียวทั้งประเทศ)
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


---

# เพิ่มในเฟส 1–4

เวลาทุกค่าเป็น UTC (ลงท้าย `Z`) · ข้อความ error เป็นภาษาไทยใน `detail` · endpoint ที่ไม่มี 🔒 เรียกได้โดยไม่ต้องล็อกอิน

## เฟส 1 — ราคาเบื้องหลัง + แจ้งเตือนราคาลดในตะกร้า

ประวัติราคาเก็บภายใน **ไม่แสดงต่อผู้ซื้อ** — ผู้ซื้อเห็นแค่ราคาก่อนลดที่ระบบคำนวณและ % ส่วนลด

**Product (ทุก endpoint ที่คืนสินค้า)**

| ฟิลด์ | ความหมาย |
|---|---|
| `original_price` | ราคาก่อนลด (ราคาขีดฆ่า) ที่ **ระบบคำนวณ** = ราคาต่ำสุดใน 30 วันก่อนราคาปัจจุบันเริ่มใช้ — `null` = ไม่ได้ลดราคา (ค่าที่ผู้ขายส่งมาใน `original_price` ถูกละเลย) |
| `discount_percent` | % ส่วนลด `null` = ไม่ต้องแสดง (ไม่ได้ลด หรือถูกซ่อนเพราะขึ้นราคา ≥ 15% ภายใน 14 วันก่อนเริ่มลด) |

กฎ: ต้องมีอย่างน้อย 1 ราคาที่ใช้จริงรวม ≥ 7 วันในหน้าต่าง 30 วัน ถึงจะมีราคาก่อนลด และใช้ราคาต่ำสุดของ **ทุกราคา** ในหน้าต่าง ·
ช่วงผ่อนผัน 30 วันแรก (ตั้งค่าได้) แค่เตือนผู้ขาย ยังไม่ซ่อน %

**Cart** — ส่ง `Authorization` มาด้วยเพื่อรับ `notices`

| ฟิลด์ | ความหมาย |
|---|---|
| `items[].price_at_add` / `items[].cart_item_id` | ราคาตอนใส่ตะกร้า / id รายการ |
| `notices[]` | แจ้งเตือนราคาลดที่ยังไม่อ่าน (guest ได้ `[]`) |

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/account/notices` 🔒 | `{unread_count, notices[]}` — `?include_read=true` รวมที่อ่านแล้ว |
| PATCH | `/account/notices/read` 🔒 | body `{ids:[...]}` หรือไม่ส่ง = ทั้งหมด → 204 |
| GET | `/seller/price-status` 🔒 | dashboard ราคาของร้าน: `grace`, `rules`, `items[]` (`ref_price, min_30d, discount_percent, discount_hidden, warnings[], carts_holding, ...`) |

Notice: สร้างเมื่อราคาลดจาก `price_at_add` ≥ 20 บาท **หรือ** ≥ 3% · ลดอีก → อัปเดตแถวเดิมและแสดงอีกครั้ง · ราคากลับขึ้นจนไม่ถึงเกณฑ์ → ลบ ·
ลบเมื่อเอาออกจากตะกร้า/checkout · เฉพาะผู้ใช้ที่ล็อกอิน · ไม่มี push/อีเมล/LINE

## เฟส 2 — สเปก ค่าส่ง เปรียบเทียบ

**Product เพิ่ม:** `brand, model_code, barcode, attributes[{key,name_th,unit,group_name,data_type,value_num,value_text,display,source}], spec_complete`
· POST/PATCH รับ `brand, model_code, barcode, attributes:[{key,value_num?,value_text?}]` (ส่ง `attributes` = แทนทั้งชุด) ·
**400** ถ้า key ไม่อยู่ในแม่แบบ / ตัวเลขติดลบ / enum ไม่อยู่ในตัวเลือก ·
`GET /products` เรียงค่าเริ่มต้น: สินค้า `spec_complete` ขยับขึ้น 3 อันดับ

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/products/{id}/spec-suggestions` 🔒 | ค่าสเปกที่ระบบเสนอจากคำอธิบาย (รอเจ้าของร้านยืนยัน) |
| POST | `/products/{id}/spec-suggestions/generate` 🔒 | ขอให้ระบบเสนอเดี๋ยวนี้ (วันละครั้ง/สินค้า → **429**; ไม่มีโมเดล → `[]`) |
| POST | `/products/{id}/spec-suggestions/confirm` 🔒 | body `{keys:[...]}` → บันทึกเป็นสเปก (`source=ai_confirmed`) |
| POST | `/products/{id}/spec-suggestions/dismiss` 🔒 | body `{keys:[...]}` → 204 |
| GET | `/products/{id}/same-model?province=` | ร้านอื่นที่ขายรุ่นนี้ (บาร์โค้ด หรือ แบรนด์+รหัสรุ่น ตรงทุกตัว) `[]` = ซ่อน |
| GET | `/products/{id}/similar?limit=3` | สินค้าหมวดเดียวกันราคาใกล้เคียง (ปุ่ม "เทียบกับสินค้าคล้ายกัน") |
| GET | `/shipping/provinces` · `/shipping/regions` | 77 จังหวัด+ภาค · รายชื่อภาค |
| GET, PUT | `/shops/me/shipping` 🔒 | `{flat_rate, free_over, days_min, days_max, region_rates:[{region,rate,days_min,days_max}]}` |
| GET, PUT | `/account/province` 🔒 | `{province, region, source}` (`source`: `account` / `order` / `null`) — PUT `{province}` |
| GET, PUT | `/account/compare-list` 🔒 | `{ids:[...]}` ถาดเปรียบเทียบที่บันทึกไว้ (สูงสุด 4) |
| GET | `/cart/{token}/shipping-quote?province=` | ค่าส่งแยกร้าน `{shops[], shipping_total, grand_total}` (engine เดียวกับ checkout) |
| GET | `/features?device_id=` | `{spec_suggest, llm_provider, chat, chat_rollout_percent, semantic_search}` |

### GET `/compare?ids=1,2,3&diff_only=true&province=`

เทียบ 1–4 ชิ้น (เกิน → **422**) ผลลัพธ์: `{province, region, same_category, summary, summary_source, missing_ids, items[], groups[]}`

- `items[]`: ราคา/ราคาก่อนลด/คะแนน/ร้าน/`shipping{fee,days_min,days_max,free_reason,free_over}`/`total`/`badges[]`
- `groups[].rows[]`: `{key,name_th,unit,better,differs,cells[{display,is_best}]}` — `display: null` = "ร้านไม่ได้ระบุ"
- ต่างหมวด: ไม่มี `groups`, ไม่มีป้าย "ถูกที่สุด", `summary_source="fixed"`
- `summary_source`: `ai` (โมเดลเขียน และทุกตัวเลขตรงกับตาราง) · `rule` (สร้างจากกฎ) · `fixed`

## เฟส 3 — แชทช่วยช้อป

| Method | Path | คำอธิบาย |
|---|---|---|
| POST | `/chat` | SSE (`text/event-stream`) body `{message, session_id?, context_sku_id?, device_id}` |
| GET | `/chat/config?device_id=&context=` | `{enabled, disclaimer, sample_questions[3], max_chars}` (`context`: `home` / `product` / `compare`) |
| POST | `/chat/feedback` | `{message_id, value}` (`up` / `down` / `null`) → 204 |
| GET | `/chat/guided?category_id=&max_price=&use=` | โหมดปุ่มเลือก (ไม่ใช้โมเดล): หมวด → งบ (`300`…`5000` หรือ `any`) → การใช้งาน → ผลลัพธ์ |

SSE event ตามลำดับ: `meta {session_id,message_id,intent,mode}` → `cards {products[]}` (ราคาสดจาก DB ส่งก่อน) → `delta {text}` (0 ครั้งหรือมากกว่า) → `done {message_id,text,suggestions,links,note,fallback}`

- `intent`: `search`, `compare`, `price`, `general_shopping`, `handoff`, `off_topic`, `blocked`, `price_trend`
- `mode`: `llm`, `cache`, `canned`, `blocked`, `fallback`
- ก่อนเริ่ม stream อาจตอบ JSON: **422** (ว่าง/ยาวเกิน 500) · **429** `{reason: rate|daily, retry_after, fallback:true}` · **503** `{fallback:true}` (ปิดแชท/อยู่นอกกลุ่ม rollout)
- `done.fallback=true` = ใช้โมเดลไม่ได้ ให้สลับเป็น `/chat/guided`

ด่านกรอง 4 ชั้น: (1) ตัดเบอร์/อีเมล/เลขบัตร + จับคำสั่งแทรก/ต่อรอง/สัญญา → ข้อความสำเร็จรูป ไม่เรียกโมเดล · (2) แปลผลเจตนาเป็น JSON ·
(3) tool อ่านอย่างเดียวที่ **เซิร์ฟเวอร์** เรียก (โมเดลสั่งเขียนไม่ได้) · (4) ตรวจขาออก: ราคา/id ต้องตรงผล tool ไม่มีคำหยาบ/คำผูกมัด ไม่ผ่าน → แสดงเฉพาะการ์ด ·
จำกัด: 30 ข้อความ/วัน (ล็อกอิน), 5/วัน (guest ต่อ IP+อุปกรณ์), 1 ข้อความ/3 วินาที · cache คำถามซ้ำ 6 ชม. · log เก็บข้อความที่ตัดข้อมูลส่วนตัวแล้ว 30 วัน

## เฟส 4 — สรุปรีวิว / อาจเป็นรุ่นเดียวกัน / ค้นหาตามความหมาย

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/products/{id}/review-summary` | `{available, review_count, min_reviews, label, praise[], complaints[], praise_quotes[], complaint_quotes[], source, generated_at}` — ตอบ 200 เสมอ (`available=false` เมื่อผู้รีวิวไม่ถึง 3 คน/ไม่มีโมเดล) |
| GET | `/products/{id}/maybe-same?province=` | ร้านอื่นที่ **อาจเป็น** รุ่นเดียวกัน: `{product_id,name,image,shop_*,price,shipping_fee,total,...,score,reasons[],label}` — แยกจาก `/same-model` เสมอ |

- สรุปรีวิว: ทุกข้อแนบ `quote` ที่เป็นข้อความจริงจากรีวิว คำคุณสมบัติ (เช่น กันน้ำ) ต้องมีในรีวิวจริง ไม่ผ่านถูกทิ้ง · cache และสร้างใหม่เมื่อรีวิวเปลี่ยน
- maybe-same: คะแนน = ชื่อ (น้ำหนักจำกัด 0.4) + แบรนด์ + สเปกที่ตรงกัน เกณฑ์ 0.6 · ตัดทิ้งเมื่อ แบรนด์/บาร์โค้ด/รหัสรุ่นต่างกัน, คำบอกรุ่นต่างกัน (Pro/Max/Mini/… หรือเลขรุ่น),
  สเปกตัวเลขต่างกัน > 10%, หรือมีคำที่หมายถึงของเลียนแบบ (เกรดเอ/ก๊อป/เทียบแท้/…) — ใช้กฎเดียวกันกับ `/same-model`
- ค้นหาตามความหมาย: เปิดด้วย `SEMANTIC_SEARCH=true` · `GET /products?search=` ได้ผลค้นด้วยคำเหมือนเดิมก่อน แล้วต่อด้วยสินค้าที่ความหมายใกล้เคียง
  (แต่ละรายการมี `match`: `keyword` / `semantic`) · ปิด/ไม่มีโมเดล/ผิดพลาด → ผลค้นหาเดิมเท่านั้น
