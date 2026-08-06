"""
Router สำหรับสินค้า (สัปดาห์ 1: คืนค่า mock data ก่อน
สัปดาห์ 2 จะย้ายไปอ่าน/เขียนจาก PostgreSQL จริงผ่าน SQLModel)
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/products", tags=["products"])

# Mock data: สินค้าตัวอย่างสไตล์ Marketplace (อ้างอิง User Journey ข้อ 2)
MOCK_PRODUCTS = [
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
        "free_shipping": True,
        "category": "ของใช้ในบ้าน",
        "description": "หมอนรองคอเนื้อเมมโมรี่โฟม นุ่มสบาย พกพาสะดวก เหมาะสำหรับเดินทางไกล",
    },
    {
        "id": 2,
        "name": "น้ำยาล้างจานสูตรมะนาว ขนาด 800 มล.",
        "price": 45,
        "original_price": 59,
        "image": "🧴",
        "shop_name": "CleanHome Official",
        "rating": 4.9,
        "sold": 15320,
        "stock": 200,
        "free_shipping": True,
        "category": "ของใช้ในบ้าน",
        "description": "น้ำยาล้างจานสูตรเข้มข้น กลิ่นมะนาวหอมสดชื่น ล้างคราบมันได้หมดจด",
    },
    {
        "id": 3,
        "name": "กระทะเคลือบไม่ติดกระทะ 28 ซม.",
        "price": 259,
        "original_price": 450,
        "image": "🍳",
        "shop_name": "KitchenPro",
        "rating": 4.7,
        "sold": 892,
        "stock": 0,
        "free_shipping": True,
        "category": "เครื่องครัว",
        "description": "กระทะเคลือบสารกันติด ทนความร้อนสูง ใช้ได้กับเตาทุกชนิดรวมถึงเตาแม่เหล็กไฟฟ้า",
    },
    {
        "id": 4,
        "name": "แปรงสีฟันไฟฟ้า ระบบ Sonic 5 โหมด",
        "price": 590,
        "original_price": 1200,
        "image": "🪥",
        "shop_name": "SmileTech Store",
        "rating": 4.6,
        "sold": 3104,
        "stock": 42,
        "free_shipping": True,
        "category": "สุขภาพและความงาม",
        "description": "แปรงสีฟันไฟฟ้าระบบสั่นความถี่สูง กันน้ำ IPX7 แบตเตอรี่ใช้ได้นาน 30 วัน",
    },
    {
        "id": 5,
        "name": "ผงซักฟอกสูตรเข้มข้น 3 กก.",
        "price": 189,
        "original_price": 220,
        "image": "🧺",
        "shop_name": "CleanHome Official",
        "rating": 4.8,
        "sold": 8760,
        "stock": 5,
        "free_shipping": False,
        "category": "ของใช้ในบ้าน",
        "description": "ผงซักฟอกสูตรเข้มข้นขจัดคราบฝังแน่น หอมติดทนนาน 24 ชั่วโมง",
    },
    {
        "id": 6,
        "name": "เก้าอี้สำนักงานเพื่อสุขภาพ ปรับระดับได้",
        "price": 2490,
        "original_price": 3990,
        "image": "🪑",
        "shop_name": "OfficeErgo",
        "rating": 4.5,
        "sold": 421,
        "stock": 8,
        "free_shipping": True,
        "category": "เฟอร์นิเจอร์",
        "description": "เก้าอี้สำนักงานรองรับสรีระ ปรับความสูง/พนักพิงได้ ล้อเลื่อนเงียบ",
    },
    {
        "id": 7,
        "name": "หลอดไฟ LED ประหยัดพลังงาน 9W (แพ็ค 4)",
        "price": 99,
        "original_price": 160,
        "image": "💡",
        "shop_name": "LightSave",
        "rating": 4.9,
        "sold": 21044,
        "stock": 150,
        "free_shipping": True,
        "category": "ของใช้ในบ้าน",
        "description": "หลอดไฟ LED แสงขาวนวล ประหยัดไฟกว่าหลอดไส้ถึง 80% อายุการใช้งานยาวนาน",
    },
    {
        "id": 8,
        "name": "เครื่องกรองน้ำติดก๊อก 3 ชั้นกรอง",
        "price": 350,
        "original_price": 590,
        "image": "🚰",
        "shop_name": "PureWater Shop",
        "rating": 4.4,
        "sold": 654,
        "stock": 3,
        "free_shipping": True,
        "category": "ของใช้ในบ้าน",
        "description": "เครื่องกรองน้ำติดหัวก๊อก กรองสนิม คลอรีน และตะกอน ติดตั้งง่ายไม่ต้องใช้ช่าง",
    },
]


@router.get("")
def list_products(search: Optional[str] = Query(None, description="คำค้นหาชื่อสินค้า")):
    """คืนรายการสินค้าทั้งหมด หรือกรองตามคำค้นหาถ้ามี query param `search`"""
    if search:
        keyword = search.strip().lower()
        return [p for p in MOCK_PRODUCTS if keyword in p["name"].lower()]
    return MOCK_PRODUCTS


@router.get("/{product_id}")
def get_product(product_id: int):
    """คืนข้อมูลสินค้ารายชิ้นตาม id"""
    product = next((p for p in MOCK_PRODUCTS if p["id"] == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="ไม่พบสินค้านี้")
    return product
