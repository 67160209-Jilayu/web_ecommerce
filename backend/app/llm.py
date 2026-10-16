"""ชั้น LlmAdapter — เรียกโมเดลภาษาผ่าน API ภายนอก สลับผู้ให้บริการได้โดยไม่แก้โค้ดส่วนอื่น

ผู้ให้บริการ (ตั้งด้วย env LLM_PROVIDER):
- auto   (ค่าเริ่มต้น) = gemini ถ้ามี GEMINI_API_KEY, ไม่งั้น none
- gemini = Gemini ผ่าน REST (ชื่อโมเดลอยู่ใน config.LLM_MODEL — ห้ามเขียนตายในโค้ด เพราะรุ่นถูกปิดบ่อย)
- fake   = ตอบแบบกำหนดได้แน่นอน ไม่เรียกเน็ต (ใช้ในเทสต์/เดโมในเครื่อง)
- none   = ไม่มี LLM → get_adapter() คืน None ทุกฟีเจอร์ต้องทำงานต่อได้แบบไม่มี AI

ทุกงานเรียกผ่าน `adapter.generate(system, messages, task=..., context=...)`
- `task` + `context` (ข้อมูลโครงสร้างที่ใช้สร้าง prompt) ให้ FakeProvider ตอบได้สมเหตุสมผลโดยไม่ต้องแกะ prompt
  ผู้ให้บริการจริงใช้แค่ system + messages
- ผลลัพธ์รูปแบบเดียว: LlmResult(text, tokens_in, tokens_out)
- ข้อผิดพลาดทุกแบบ (ไม่มี key, 429, 5xx, timeout) → LlmUnavailable ให้ผู้เรียกสลับไปโหมดสำรอง
"""
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, Iterator, List, Optional

from app import config


class LlmUnavailable(Exception):
    """LLM ใช้ไม่ได้ตอนนี้ (ไม่มี key / โควตาเต็ม / ล่ม) — ผู้เรียกต้องมีทางสำรองเสมอ"""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


@dataclass
class LlmResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


Message = Dict[str, str]  # {"role": "user"|"model", "text": "..."}


class LlmAdapter:
    name = "base"

    def generate(
        self,
        system: str,
        messages: List[Message],
        *,
        task: str,
        context: Optional[dict] = None,
        json_mode: bool = False,
        max_tokens: int = 300,
    ) -> LlmResult:
        raise NotImplementedError

    def embed(self, texts: List[str]) -> List[List[float]]:
        """เวกเตอร์ความหมายของข้อความ (ใช้ค้นหาตามความหมาย) — ผู้ให้บริการที่ไม่รองรับ raise LlmUnavailable"""
        raise LlmUnavailable("ผู้ให้บริการนี้ไม่รองรับ embedding")

    def stream(
        self,
        system: str,
        messages: List[Message],
        *,
        task: str,
        context: Optional[dict] = None,
        max_tokens: int = 300,
    ) -> Iterator[str]:
        """ค่าเริ่มต้น: เรียกครั้งเดียวแล้วแบ่งเป็นชิ้นๆ (ผู้ให้บริการที่ stream ได้จริงจะ override)"""
        text = self.generate(system, messages, task=task, context=context, max_tokens=max_tokens).text
        for i in range(0, len(text), 24):
            yield text[i:i + 24]


# =====================================================================
# Gemini (REST)
# =====================================================================

class GeminiProvider(LlmAdapter):
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str, timeout: float = 20.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def _body(self, system, messages, json_mode, max_tokens) -> bytes:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "model" if m["role"] == "model" else "user", "parts": [{"text": m["text"]}]}
                for m in messages
            ],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
        }
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _request(self, url: str, data: bytes):
        # ส่ง key ทาง header (ไม่ใส่ใน URL กันหลุดไปใน log)
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            raise LlmUnavailable(f"Gemini HTTP {err.code}", status=err.code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise LlmUnavailable(f"Gemini ไม่ตอบสนอง: {err}") from None

    @staticmethod
    def _text_of(payload: dict) -> str:
        parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    def generate(self, system, messages, *, task, context=None, json_mode=False, max_tokens=300):
        url = f"{self.BASE}/{self.model}:generateContent"
        with self._request(url, self._body(system, messages, json_mode, max_tokens)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        usage = payload.get("usageMetadata", {})
        return LlmResult(
            text=self._text_of(payload),
            tokens_in=usage.get("promptTokenCount", 0),
            tokens_out=usage.get("candidatesTokenCount", 0),
        )

    def embed(self, texts):
        model = config.LLM_EMBED_MODEL
        url = f"{self.BASE}/{model}:batchEmbedContents"
        body = {"requests": [{"model": f"models/{model}", "content": {"parts": [{"text": t[:2000]}]}}
                             for t in texts]}
        with self._request(url, json.dumps(body, ensure_ascii=False).encode("utf-8")) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return [e.get("values", []) for e in payload.get("embeddings", [])]

    def stream(self, system, messages, *, task, context=None, max_tokens=300):
        url = f"{self.BASE}/{self.model}:streamGenerateContent?alt=sse"
        with self._request(url, self._body(system, messages, False, max_tokens)) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if line.startswith("data:"):
                    try:
                        chunk = self._text_of(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        continue
                    if chunk:
                        yield chunk


# =====================================================================
# Fake (กำหนดผลได้แน่นอน — ไม่ใช้เน็ต)
# =====================================================================

FakeHandler = Callable[[str, List[Message], dict], str]
FAKE_HANDLERS: Dict[str, FakeHandler] = {}


def fake_handler(task: str):
    """ลงทะเบียนวิธีตอบของ FakeProvider ต่องาน (แต่ละโมดูลลงทะเบียนของตัวเอง)"""
    def deco(fn: FakeHandler) -> FakeHandler:
        FAKE_HANDLERS[task] = fn
        return fn
    return deco


def fake_vector(text: str, dim: int = 256) -> List[float]:
    """เวกเตอร์กำหนดผลได้แน่นอนจาก char-trigram (ข้อความคล้าย → เวกเตอร์คล้าย) ไม่ใช้เน็ต"""
    import hashlib
    import math

    t = re.sub(r"\s+", " ", (text or "").casefold()).strip()
    vec = [0.0] * dim
    grams = [t[i:i + 3] for i in range(max(1, len(t) - 2))]
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeProvider(LlmAdapter):
    name = "fake"

    def embed(self, texts):
        return [fake_vector(t) for t in texts]

    def generate(self, system, messages, *, task, context=None, json_mode=False, max_tokens=300):
        handler = FAKE_HANDLERS.get(task)
        text = handler(system, messages, context or {}) if handler else ""
        return LlmResult(text=text, tokens_in=sum(len(m["text"]) for m in messages) // 4,
                         tokens_out=len(text) // 4)


# =====================================================================
# เลือกผู้ให้บริการ
# =====================================================================

def provider_name() -> str:
    p = (config.LLM_PROVIDER or "auto").strip().lower()
    if p == "auto":
        return "gemini" if config.GEMINI_API_KEY else "none"
    return p


def get_adapter() -> Optional[LlmAdapter]:
    """คืน adapter ตาม config หรือ None ถ้าไม่มี LLM (ทุกฟีเจอร์ต้องรองรับกรณีนี้)"""
    name = provider_name()
    if name == "fake":
        return FakeProvider()
    if name == "gemini":
        if not config.GEMINI_API_KEY:
            return None
        return GeminiProvider(config.GEMINI_API_KEY, config.LLM_MODEL, timeout=config.LLM_TIMEOUT)
    return None


def parse_json(text: str) -> Optional[dict]:
    """ดึง JSON object จากคำตอบโมเดล (เผื่อโมเดลห่อด้วย ```json ... ```)"""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
