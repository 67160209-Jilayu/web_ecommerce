"""จัดการไฟล์ที่ผู้ขายอัปโหลด (รูป/วิดีโอสินค้า)

แยกออกมาเป็นโมดูลกลางเพื่อให้ทั้ง router (ตอนอัปโหลด) และ crud (ตอนลบไฟล์ที่ไม่ใช้แล้ว)
ใช้ค่าเดียวกันได้ โดยไม่ต้อง import ข้ามกันจนเกิด circular import
"""
from pathlib import Path
from typing import Iterable

from app.config import UPLOAD_DIR

UPLOAD_URL_PREFIX = "/uploads/"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def path_from_url(url: str) -> Path | None:
    """แปลง URL (/uploads/xxx.jpg) เป็น path จริงบนดิสก์

    คืน None ถ้า URL ไม่ได้ชี้มาที่โฟลเดอร์อัปโหลดของเรา หรือพยายามหลุดออกนอกโฟลเดอร์
    (กัน path traversal จาก URL ที่ถูกแก้ในฐานข้อมูล)
    """
    if not url or not url.startswith(UPLOAD_URL_PREFIX):
        return None

    candidate = (UPLOAD_DIR / url[len(UPLOAD_URL_PREFIX):]).resolve()
    try:
        candidate.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None
    return candidate


def delete_files(urls: Iterable[str]) -> int:
    """ลบไฟล์ตาม URL ที่ให้มา คืนจำนวนไฟล์ที่ลบได้จริง

    ผู้เรียกต้องมั่นใจแล้วว่าไม่มีสินค้าชิ้นไหนอ้างอิง URL เหล่านี้อยู่
    """
    removed = 0
    for url in urls:
        path = path_from_url(url)
        if path is None:
            continue
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass          # ไฟล์หายไปแล้ว ถือว่าสำเร็จ
        except OSError:
            pass          # ลบไม่ได้ (สิทธิ์/ดิสก์) ไม่ควรทำให้การบันทึกสินค้าล้มเหลว
    return removed
