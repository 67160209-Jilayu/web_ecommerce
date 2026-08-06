"""ใส่ข้อมูลตัวอย่างตอนเริ่มระบบครั้งแรก (ย้ายมาจาก mock data ของสัปดาห์ 1)
ทำงานเฉพาะตอนฐานข้อมูลยังว่างอยู่ ไม่ทับข้อมูลที่มีอยู่แล้ว
"""
from sqlmodel import Session, select

from app import models

DEMO_SHOPS = [
    {"name": "HomeComfort Shop", "rating": 4.8, "is_verified": True},
    {"name": "CleanHome Official", "rating": 4.9, "is_verified": True},
    {"name": "KitchenPro", "rating": 4.7, "is_verified": False},
    {"name": "SmileTech Store", "rating": 4.6, "is_verified": True},
    {"name": "OfficeErgo", "rating": 4.5, "is_verified": False},
    {"name": "LightSave", "rating": 4.9, "is_verified": True},
    {"name": "PureWater Shop", "rating": 4.4, "is_verified": False},
]

# (shop_index, name, price, original_price, image, category, description, rating, sold, stock, free_shipping)
DEMO_PRODUCTS = [
    (0, "หมอนรองคอเมมโมรี่โฟม รุ่นเดินทาง", 199, 350, "🧸", "ของใช้ในบ้าน",
     "หมอนรองคอเนื้อเมมโมรี่โฟม นุ่มสบาย พกพาสะดวก เหมาะสำหรับเดินทางไกล", 4.8, 2431, 15, True),
    (1, "น้ำยาล้างจานสูตรมะนาว ขนาด 800 มล.", 45, 59, "🧴", "ของใช้ในบ้าน",
     "น้ำยาล้างจานสูตรเข้มข้น กลิ่นมะนาวหอมสดชื่น ล้างคราบมันได้หมดจด", 4.9, 15320, 200, True),
    (2, "กระทะเคลือบไม่ติดกระทะ 28 ซม.", 259, 450, "🍳", "เครื่องครัว",
     "กระทะเคลือบสารกันติด ทนความร้อนสูง ใช้ได้กับเตาทุกชนิดรวมถึงเตาแม่เหล็กไฟฟ้า", 4.7, 892, 0, True),
    (3, "แปรงสีฟันไฟฟ้า ระบบ Sonic 5 โหมด", 590, 1200, "🪥", "สุขภาพและความงาม",
     "แปรงสีฟันไฟฟ้าระบบสั่นความถี่สูง กันน้ำ IPX7 แบตเตอรี่ใช้ได้นาน 30 วัน", 4.6, 3104, 42, True),
    (1, "ผงซักฟอกสูตรเข้มข้น 3 กก.", 189, 220, "🧺", "ของใช้ในบ้าน",
     "ผงซักฟอกสูตรเข้มข้นขจัดคราบฝังแน่น หอมติดทนนาน 24 ชั่วโมง", 4.8, 8760, 5, False),
    (4, "เก้าอี้สำนักงานเพื่อสุขภาพ ปรับระดับได้", 2490, 3990, "🪑", "เฟอร์นิเจอร์",
     "เก้าอี้สำนักงานรองรับสรีระ ปรับความสูง/พนักพิงได้ ล้อเลื่อนเงียบ", 4.5, 421, 8, True),
    (5, "หลอดไฟ LED ประหยัดพลังงาน 9W (แพ็ค 4)", 99, 160, "💡", "ของใช้ในบ้าน",
     "หลอดไฟ LED แสงขาวนวล ประหยัดไฟกว่าหลอดไส้ถึง 80% อายุการใช้งานยาวนาน", 4.9, 21044, 150, True),
    (6, "เครื่องกรองน้ำติดก๊อก 3 ชั้นกรอง", 350, 590, "🚰", "ของใช้ในบ้าน",
     "เครื่องกรองน้ำติดหัวก๊อก กรองสนิม คลอรีน และตะกอน ติดตั้งง่ายไม่ต้องใช้ช่าง", 4.4, 654, 3, True),
]


def seed_if_empty(session: Session) -> None:
    already_has_data = session.exec(select(models.Shop)).first()
    if already_has_data is not None:
        return

    shops = [models.Shop(**s) for s in DEMO_SHOPS]
    session.add_all(shops)
    session.commit()
    for shop in shops:
        session.refresh(shop)

    for (
        shop_index,
        name,
        price,
        original_price,
        image,
        category,
        description,
        rating,
        sold,
        stock,
        free_shipping,
    ) in DEMO_PRODUCTS:
        session.add(
            models.Product(
                shop_id=shops[shop_index].id,
                name=name,
                price=price,
                original_price=original_price,
                image=image,
                category=category,
                description=description,
                rating=rating,
                sold=sold,
                stock=stock,
                free_shipping=free_shipping,
            )
        )
    session.commit()
