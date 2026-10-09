"""ด่านกรองของแชท (เฟส 3) — ชั้น 1 (ขาเข้า), ชั้น 2 (แปลผลจำแนกเจตนา), ชั้น 4 (ขาออก)

ชั้น 3 (tool อ่านอย่างเดียว) อยู่ใน app/chat.py
ทุกฟังก์ชันเป็น pure function เรียกตรงได้ในชุดทดสอบ
"""
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

from app import config, llm

INTENTS = ("search", "compare", "price", "general_shopping", "handoff", "off_topic")

OFF_TOPIC_TEXT = "เรื่องนี้นอกเหนือที่ช่วยได้ครับ ผมช่วยหาและเปรียบเทียบสินค้าได้ ลองถามแบบนี้ดูไหมครับ"
BLOCKED_TEXT = (
    "ขออภัยครับ ผมช่วยได้เฉพาะการหาและเปรียบเทียบสินค้า "
    "ไม่สามารถต่อรองราคา ให้ส่วนลด หรือเปลี่ยนบทบาทได้ครับ"
)
PRICE_TREND_TEXT = (
    "ผมไม่มีข้อมูลแนวโน้มราคาครับ ราคา ณ ตอนนี้ดูได้ที่หน้าสินค้า "
    "และตอนนี้ยังไม่มีโปรหรือคูปองที่ใช้ได้"
)
HANDOFF_TEXT = (
    "เรื่องคำสั่งซื้อ การคืนเงิน หรือบัญชี ผมตอบแทนไม่ได้ครับ "
    "ดูรายละเอียดได้ที่หน้าคำสั่งซื้อของคุณ หรือหน้านโยบายด้านล่างนี้ครับ"
)
SAMPLE_QUESTIONS = [
    "หาหูฟังไร้สายงบไม่เกิน 1,500 บาท",
    "กระทะเคลือบกันติดใช้กับเตาแม่เหล็กไฟฟ้าได้",
    "สินค้าสองชิ้นนี้ต่างกันยังไง",
]
HANDOFF_LINKS = [
    {"label": "คำสั่งซื้อของฉัน", "url": "/pages/orders.html"},
    {"label": "นโยบายและเกณฑ์การแนะนำ", "url": "/pages/chat-policy.html"},
]
DISCLAIMER = "ตอบโดย AI อาจผิดพลาดได้ ราคาและเงื่อนไขที่ใช้จริงดูที่หน้าสินค้า อย่าใส่ข้อมูลส่วนตัว"

# =====================================================================
# ชั้น 1: ขาเข้า (ไม่เสีย token)
# =====================================================================

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_NATIONAL_ID = re.compile(r"(?<!\d)\d[ -]?\d{4}[ -]?\d{5}[ -]?\d{2}[ -]?\d(?!\d)")
_PHONE = re.compile(r"(?:\+66[ -]?|(?<!\d)0)(?:\d[ -]?){7,8}\d(?!\d)")

# คำสั่งแทรก / เปลี่ยนบทบาท / ขอดู system prompt / ต่อรองราคา / ขอส่วนลด / คู่แข่ง
_BLOCK_PATTERNS = [
    (r"ignore (all |the )?(previous|above|prior)|disregard (all |the )?(previous|above)|forget (all |your )?(previous )?instructions", "injection"),
    (r"ลืม(คำสั่ง|ที่บอก|กฎ)|ไม่ต้องสนใจ(คำสั่ง|กฎ)|ยกเลิกคำสั่ง|ข้ามกฎ", "injection"),
    (r"system prompt|ระบบพรอมต์|ซิสเต็มพรอมต์|พรอมต์ของคุณ|คำสั่งตั้งต้น|developer mode|jailbreak|\bDAN\b", "system_prompt"),
    (r"you are now|act as|pretend (to be|you)|role[- ]?play|สวมบทบาท|แกล้งทำเป็น|ทำตัวเป็น|ตอนนี้คุณคือ|สมมติว่าคุณเป็น|เล่นบท", "role_play"),
    (r"ต่อรอง|ลดราคาให้(หน่อย|ได้ไหม|ที|ผม|ฉัน|หนู)|ขอ(ส่วน)?ลด(ราคา)?(หน่อย|ได้ไหม|เพิ่ม)|ขอโค้ด|ขอคูปอง|แจกโค้ด|ให้ส่วนลด|ราคาพิเศษให้|ขายให้(ผม|ฉัน|หนู)?\s*\d+\s*บาท|ลดเหลือ\s*\d+|discount code|coupon code|\$1(?!\d)", "negotiation"),
    (r"สัญญา(ว่า|ได้ไหม|สิ)|รับปาก|การันตีให้|promise", "promise"),
    (r"shopee|lazada|ลาซาด้า|ช้อปปี้|amazon|อเมซอน|jd central|tiktok shop|temu|aliexpress", "competitor"),
]
_BLOCK_RE = [(re.compile(p, re.I), reason) for p, reason in _BLOCK_PATTERNS]

_PRICE_TREND_RE = re.compile(
    r"เคยถูกกว่า|เคยลด|ราคาย้อนหลัง|ประวัติราคา|แนวโน้มราคา|ราคาจะ(ลด|ขึ้น)|จะลดราคา(ไหม|มั้ย|อีก)|"
    r"(ควร|น่า)รอ(โปร|ลด|ราคา|ก่อน)|รอโปร|รอ(ช่วง)?ลดราคา|ถูกลงไหม|ถูกลงมั้ย|ลดอีกไหม|"
    r"price history|cheaper before|wait for (a )?(sale|discount)|will the price drop",
    re.I,
)


@dataclass
class InputCheck:
    ok: bool
    masked_text: str = ""
    error: Optional[str] = None
    blocked: bool = False
    block_reason: Optional[str] = None


def mask_pii(text: str) -> str:
    """ตัดข้อมูลส่วนตัวก่อนส่งให้โมเดล/เก็บ log (ลำดับสำคัญ: เลขยาวก่อน)"""
    text = _EMAIL.sub("[อีเมล]", text)
    text = _NATIONAL_ID.sub("[เลขบัตรประชาชน]", text)
    text = _CARD.sub("[เลขบัตร]", text)
    text = _PHONE.sub("[เบอร์โทร]", text)
    return text


def check_input(text: Optional[str]) -> InputCheck:
    """ชั้น 1: ความยาว + ตัดข้อมูลส่วนตัว + จับคำสั่งแทรก/ต่อรอง/เปลี่ยนบทบาท"""
    text = (text or "").strip()
    if not text:
        return InputCheck(ok=False, error="กรุณาพิมพ์ข้อความ")
    if len(text) > config.CHAT_MAX_CHARS:
        return InputCheck(ok=False, error=f"ข้อความยาวเกิน {config.CHAT_MAX_CHARS} ตัวอักษร")
    masked = mask_pii(text)
    for rx, reason in _BLOCK_RE:
        if rx.search(text):
            return InputCheck(ok=True, masked_text=masked, blocked=True, block_reason=reason)
    return InputCheck(ok=True, masked_text=masked)


def detect_price_trend(text: str) -> bool:
    """คำถามแนวโน้ม/ประวัติราคา — แชทไม่มีข้อมูลนี้ ตอบสำเร็จรูป"""
    return bool(_PRICE_TREND_RE.search(text or ""))


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold()).strip(" ?!.ๆ")


# =====================================================================
# ชั้น 2: แปลผลจำแนกเจตนา
# =====================================================================

def parse_intent(raw: str) -> dict:
    """{intent, filters, compare_ids} — อะไรที่ผิดรูปแบบถือเป็น off_topic (ปลอดภัยไว้ก่อน)"""
    data = llm.parse_json(raw) or {}
    intent = data.get("intent")
    if intent not in INTENTS:
        intent = "off_topic"
    f = data.get("filters") if isinstance(data.get("filters"), dict) else {}
    filters = {}
    for k in ("min_price", "max_price"):
        try:
            if f.get(k) is not None:
                filters[k] = max(0, int(float(f[k])))
        except (TypeError, ValueError):
            pass
    if isinstance(f.get("category"), str):
        filters["category"] = f["category"].strip()[:40]
    if isinstance(f.get("keywords"), str):
        filters["keywords"] = f["keywords"].strip()[:60]
    if f.get("sort") in ("price_asc", "price_desc", "rating", "popular"):
        filters["sort"] = f["sort"]
    if isinstance(f.get("attributes"), dict):
        filters["attributes"] = {
            str(k)[:40]: v for k, v in list(f["attributes"].items())[:5]
            if isinstance(v, (str, int, float, bool))
        }
    ids = []
    for x in data.get("compare_ids") or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            pass
    return {"intent": intent, "filters": filters, "compare_ids": ids[:4]}


# =====================================================================
# ชั้น 4: ขาออก
# =====================================================================

_PROFANITY = [
    "เหี้ย", "ควย", "เย็ด", "ไอ้สัตว์", "ชิบหาย", "มึง", "แม่ง", "ส้นตีน",
    "fuck", "shit", "bitch", "damn",
]
_COMMIT_WORDS = ["สัญญา", "รับประกัน", "ผูกพัน", "การันตี", "guarantee", "promise"]

# ราคา: ฿1,290 | 1,290 บาท | 1290.- | THB 1290
_PRICE_RE = re.compile(
    r"(?:฿|THB\s?)\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s?(?:บาท|baht|THB|\.-)", re.I
)
_ID_RE = re.compile(r"\[#(\d+)\]|สินค้า\s?#(\d+)|product[_ ]?id\s?[:=]?\s?(\d+)", re.I)


@dataclass
class OutputCheck:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    prices: List[int] = field(default_factory=list)


def extract_prices(text: str) -> List[int]:
    out = []
    for m in _PRICE_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").replace(",", "")
        try:
            out.append(int(float(raw)))
        except ValueError:
            pass
    return out


def check_output(text: str, allowed_prices: Iterable[int], allowed_ids: Iterable[int]) -> OutputCheck:
    """ชั้น 4: ทุกราคาในคำตอบต้องตรงกับผล tool, product id ที่อ้างต้องมีอยู่จริง, ไม่มีคำหยาบ/คำผูกมัด"""
    reasons = []
    allowed_p: Set[int] = {int(p) for p in allowed_prices}
    allowed_i: Set[int] = {int(i) for i in allowed_ids}
    prices = extract_prices(text)
    bad = [p for p in prices if p not in allowed_p]
    if bad:
        reasons.append(f"price_mismatch:{bad}")
    for m in _ID_RE.finditer(text or ""):
        pid = int(next(g for g in m.groups() if g))
        if pid not in allowed_i:
            reasons.append(f"unknown_product:{pid}")
    low = (text or "").casefold()
    if any(w in low for w in _PROFANITY):
        reasons.append("profanity")
    if any(w in low for w in _COMMIT_WORDS):
        reasons.append("commitment_word")
    return OutputCheck(ok=not reasons, reasons=reasons, prices=prices)
