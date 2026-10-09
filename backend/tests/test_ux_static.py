"""UX สำหรับทุกวัย — ตรวจแบบ static (ไม่ได้รันเบราว์เซอร์จริง)

ครอบคลุมเท่าที่ตรวจจากซอร์สได้: label ของช่องกรอก, alt ของรูป, ปุ่มไอคอนต้องมีชื่อ,
ขนาดตัวอักษร, การไม่บล็อกการซูม, ขนาดปุ่ม ≥44px, prefers-reduced-motion, contrast ของสีหลัก
ตรวจทั้ง HTML ในไฟล์ และ HTML ที่ JS สร้างจาก template string (`...`)

สิ่งที่ตรวจแบบ static ไม่ได้ (ต้องให้คน/เบราว์เซอร์ตรวจ): 200% zoom, จอ 360px, keyboard flow,
focus ที่มองเห็น, ความเข้าใจภาษา
"""
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
HTML_FILES = sorted([FRONTEND / "index.html", *(FRONTEND / "pages").glob("*.html")])
JS_FILES = sorted(FRONTEND.glob("js/*.js"))
CSS = (FRONTEND / "css" / "style.css").read_text(encoding="utf-8")

DYN = "⟦dyn⟧"   # แทน ${...} — ค่าที่ JS ใส่ตอนรัน (ถือว่ามีข้อความ/ค่า)
MIN_FONT_PX = 12        # ต่ำกว่านี้อ่านยากสำหรับผู้สูงอายุ — ห้ามเด็ดขาด
BASE_FONT_PX = 16
REM = 16


def rel(p: Path) -> str:
    return p.relative_to(FRONTEND).as_posix()


# ------------------------------------------------------------------ HTML extraction

def html_sources():
    """[(ชื่อแหล่ง, html)] — ทั้งไฟล์ HTML และ template string ใน <script>/JS"""
    out = []
    for f in HTML_FILES:
        text = f.read_text(encoding="utf-8")
        out.append((rel(f), re.sub(r"<script\b.*?</script>", "", text, flags=re.S | re.I)))
        for i, script in enumerate(re.findall(r"<script\b[^>]*>(.*?)</script>", text, flags=re.S | re.I)):
            out += [(f"{rel(f)}<script#{i}>`{j}`", t) for j, t in enumerate(_templates(script))]
    for f in JS_FILES:
        out += [(f"{rel(f)}`{j}`", t) for j, t in enumerate(_templates(f.read_text(encoding="utf-8")))]
    return out


def _templates(js: str):
    """template literal ที่มี tag HTML — แทน ${...} ด้วย X (รองรับซ้อน 1 ชั้นแบบหยาบ)"""
    out = []
    for m in re.finditer(r"`((?:\\.|\$\{(?:[^{}`]|`[^`]*`|\{[^{}]*\})*\}|[^`\\])*)`", js, flags=re.S):
        body = m.group(1)
        if "<" not in body or not re.search(r"<[a-zA-Z]", body):
            continue
        body = re.sub(r"\$\{(?:[^{}`]|`[^`]*`|\{[^{}]*\})*\}", DYN, body)
        out.append(body)
    return out


class Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inputs, self.imgs, self.buttons, self.label_for = [], [], [], set()
        self._label_depth = 0
        self._btn = None
        self.metas = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            self.inputs.append((tag, a, self._label_depth > 0))
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "meta":
            self.metas.append(a)
        if tag in ("button",) or (tag == "a" and a.get("role") == "button"):
            self._btn = {"attrs": a, "text": ""}
        if tag == "img" and self._btn is not None and a.get("alt"):
            self._btn["text"] += a["alt"]

    def handle_endtag(self, tag):
        if tag == "label" and self._label_depth:
            self._label_depth -= 1
        if tag == "button" and self._btn is not None:
            self.buttons.append(self._btn)
            self._btn = None

    def handle_data(self, data):
        if self._btn is not None:
            self._btn["text"] += data


def parse(html):
    c = Collector()
    c.feed(html)
    c.close()
    return c


def _named(a: dict) -> bool:
    return any(a.get(k) for k in ("aria-label", "aria-labelledby", "title"))


# ------------------------------------------------------------------ labels / alt / buttons

def test_every_input_has_label():
    problems = []
    for src, html in html_sources():
        c = parse(html)
        for tag, a, wrapped in c.inputs:
            if a.get("type") in ("hidden", "submit", "button", "reset", "image") or "hidden" in a:
                continue
            if DYN in (a.get("id") or "") and _dynamic_label_exists(src):
                continue
            if wrapped or _named(a) or (a.get("id") and a["id"] in c.label_for):
                continue
            if a.get("id") and DYN not in a["id"] and _label_for_anywhere(a["id"]):
                continue
            problems.append(f"{src}: <{tag} {_short(a)}>")
    assert not problems, "ช่องกรอกที่ไม่มี label:\n" + "\n".join(problems)


_ALL_TEXT = None


def _dynamic_label_exists(src):
    """id สร้างตอนรัน (เช่น attr-${key}) → ยอมรับถ้าไฟล์เดียวกันมี <label for="...${...}">"""
    f = FRONTEND / src.split("<")[0].split("`")[0]
    return re.search(r'<label[^>]*for="[^"]*\$\{', f.read_text(encoding="utf-8")) is not None


def _label_for_anywhere(id_):
    """label for=... อาจอยู่ในไฟล์เดียวกันแต่คนละ template"""
    global _ALL_TEXT
    if _ALL_TEXT is None:
        _ALL_TEXT = "\n".join(p.read_text(encoding="utf-8") for p in HTML_FILES + JS_FILES)
    return re.search(r'for="%s"' % re.escape(id_), _ALL_TEXT) is not None


def _short(a):
    return " ".join(f'{k}="{v}"' for k, v in a.items() if k in ("id", "name", "type", "class", "placeholder"))


def test_every_img_has_alt():
    problems = []
    for src, html in html_sources():
        for a in parse(html).imgs:
            if "alt" not in a:  # alt="" อนุญาต (รูปตกแต่ง)
                problems.append(f"{src}: <img {_short(a)} src={a.get('src', '')[:40]}>")
    assert not problems, "รูปที่ไม่มี alt:\n" + "\n".join(problems)


ICON_ONLY = re.compile(r"^[\s×✕✖✓✔+\-–—<>‹›«»←→↑↓⟨⟩❮❯▲▼☰⋯…🔔🛒👍👎💬🗑️🗑✏️⚙️🔍❌⭐★☆]*$")


def test_icon_only_buttons_have_accessible_name():
    problems = []
    for src, html in html_sources():
        for b in parse(html).buttons:
            text = b["text"].strip()
            if DYN in text:
                continue  # ข้อความใส่ตอนรัน — ตรวจแบบ static ไม่ได้
            if ICON_ONLY.match(text) and not _named(b["attrs"]):
                problems.append(f"{src}: <button {_short(b['attrs'])}>{text!r}")
    assert not problems, "ปุ่มไอคอนที่ไม่มี aria-label/title/ข้อความ:\n" + "\n".join(problems)


# ------------------------------------------------------------------ zoom / font

@pytest.mark.parametrize("page", HTML_FILES, ids=rel)
def test_viewport_allows_zoom(page):
    metas = [m for m in parse(page.read_text(encoding="utf-8")).metas if m.get("name") == "viewport"]
    assert metas, "ไม่มี meta viewport"
    content = metas[0].get("content", "").replace(" ", "").lower()
    assert "user-scalable=no" not in content and "user-scalable=0" not in content
    m = re.search(r"maximum-scale=([\d.]+)", content)
    assert not m or float(m.group(1)) >= 5, content


def _rules(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        yield m.group(1).strip(), m.group(2)


def _px(value: str):
    v = value.strip().lower()
    m = re.match(r"^([\d.]+)(px|rem|em)$", v)
    if not m:
        return None
    n = float(m.group(1))
    return n if m.group(2) == "px" else n * REM


def test_base_font_size_at_least_16px():
    for sel, body in _rules(CSS):
        sels = [s.strip() for s in sel.split(",")]
        if "html" in sels or "body" in sels or ":root" in sels:
            m = re.search(r"(?<![-\w])font-size\s*:\s*([^;]+)", body)
            if m:
                v = m.group(1).strip()
                px = _px(v) if not v.endswith("%") else float(v[:-1]) / 100 * 16
                assert px is None or px >= BASE_FONT_PX, f"{sel} font-size {v}"


def test_no_tiny_fonts():
    """ตัวอักษรต้อง ≥ 12px ทุกที่ (clamp() ใช้ค่าต่ำสุด)"""
    problems = []
    for sel, body in _rules(CSS):
        for m in re.finditer(r"(?<![-\w])font-size\s*:\s*([^;]+)", body):
            v = m.group(1).strip()
            cm = re.match(r"clamp\(\s*([^,]+),", v)
            px = _px(cm.group(1)) if cm else _px(v)
            if px is not None and px < MIN_FONT_PX:
                problems.append(f"{sel[:60]} → {v} (~{px:.1f}px)")
    assert not problems, f"ตัวอักษรเล็กกว่า {MIN_FONT_PX}px:\n" + "\n".join(problems)


def test_inline_styles_no_tiny_fonts():
    problems = []
    for f in HTML_FILES + JS_FILES:
        for m in re.finditer(r"font-size\s*:\s*([\d.]+(?:px|rem|em))", f.read_text(encoding="utf-8")):
            px = _px(m.group(1))
            if px is not None and px < MIN_FONT_PX:
                problems.append(f"{rel(f)}: font-size {m.group(1)}")
    assert not problems, "\n".join(problems)


# ------------------------------------------------------------------ targets / motion / contrast

def _var(name):
    m = re.search(r"--%s\s*:\s*([^;]+);" % re.escape(name), CSS)
    return m.group(1).strip() if m else None


def _px_resolved(value):
    v = value.strip()
    m = re.match(r"var\(--([\w-]+)\)", v)
    if m:
        v = _var(m.group(1)) or ""
    return _px(v)


def test_buttons_min_touch_target():
    """ปุ่ม/ลิงก์ที่กดได้ต้องสูง ≥ 44px: ต้องมีกฎพื้นฐาน และห้ามมีกฎไหนตั้ง min-height ต่ำกว่า 44px ให้ปุ่ม"""
    base_ok = False
    small = []
    for sel, body in _rules(CSS):
        sels = [x.strip() for x in sel.split(",")]
        for m in re.finditer(r"(?<![-\w])min-height\s*:\s*([^;]+)", body):
            px = _px_resolved(m.group(1))
            if px is None:
                continue
            buttonish = [x for x in sels if re.search(r"(^|[\s.>])(button|btn|chip|tab-btn)", x)]
            if (".btn" in sels or "button" in sels) and px >= 44:
                base_ok = True
            if buttonish and px < 44:
                small.append(f"{', '.join(buttonish)[:60]} → min-height {m.group(1).strip()} (~{px:.0f}px)")
    assert base_ok, "ไม่มีกฎ button/.btn ที่ตั้ง min-height ≥ 44px"
    assert not small, "ปุ่มที่เล็กกว่า 44px:\n" + "\n".join(small)


def test_respects_reduced_motion():
    if re.search(r"(animation|transition)\s*:", CSS):
        assert "prefers-reduced-motion" in CSS


def _hex(c):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _lum(rgb):
    lin = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((_lum(_hex(a)), _lum(_hex(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _root_vars():
    root = re.search(r":root\s*\{([^}]*)\}", CSS).group(1)
    return dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\b", root))


def test_text_color_contrast_aa():
    v = _root_vars()
    backgrounds = [x for x in (v.get("sky"), "#ffffff") if x]
    text_vars = [k for k in v if k in ("ink", "muted", "text", "ink-2", "muted-2")]
    assert "ink" in text_vars
    problems = []
    for k in text_vars:
        for bg in backgrounds:
            r = contrast(v[k], bg)
            if r < 4.5:
                problems.append(f"--{k} {v[k]} บน {bg}: {r:.2f}:1")
    assert not problems, "contrast ต่ำกว่า WCAG AA 4.5:1:\n" + "\n".join(problems)
