"""ค่าตั้งค่าที่เปลี่ยนได้ขณะระบบทำงาน (ไม่ต้อง deploy) — เก็บในตาราง app_setting ทับค่า env

ใช้กับสวิตช์ปิดแชททันที และ % การเปิดให้ผู้ใช้ (rollout)
    python -m app.settings get
    python -m app.settings set chat_enabled false
    python -m app.settings set chat_rollout_percent 5
    python -m app.settings unset chat_enabled          (กลับไปใช้ค่าจาก env)
"""
import hashlib
import sys
from typing import Optional

from sqlmodel import Session

from app import config, models

KNOWN = {
    "chat_enabled": ("CHAT_ENABLED", "bool"),
    "chat_rollout_percent": ("CHAT_ROLLOUT_PERCENT", "int"),
    "semantic_search": ("SEMANTIC_SEARCH", "bool"),
}


def _parse(kind: str, raw: str):
    if kind == "bool":
        if raw.strip().lower() in ("1", "true", "yes", "on"):
            return True
        if raw.strip().lower() in ("0", "false", "no", "off"):
            return False
        raise ValueError("ต้องเป็น true/false")
    value = int(raw)
    if not 0 <= value <= 100:
        raise ValueError("ต้องอยู่ระหว่าง 0-100")
    return value


def get(session: Session, key: str):
    env_name, kind = KNOWN[key]
    row = session.get(models.AppSetting, key)
    if row is not None:
        try:
            return _parse(kind, row.value)
        except ValueError:
            pass
    return getattr(config, env_name)


def set_value(session: Session, key: str, raw: Optional[str]) -> None:
    if key not in KNOWN:
        raise KeyError(f"ไม่รู้จัก {key} (มี: {', '.join(KNOWN)})")
    row = session.get(models.AppSetting, key)
    if raw is None:
        if row is not None:
            session.delete(row)
    else:
        _parse(KNOWN[key][1], raw)
        row = row or models.AppSetting(key=key, value=raw)
        row.value = raw
        session.add(row)
    session.commit()


def chat_bucket(user_id: Optional[int], device_id: Optional[str]) -> int:
    ident = f"user:{user_id}" if user_id is not None else f"device:{device_id or ''}"
    return int(hashlib.sha1(ident.encode()).hexdigest(), 16) % 100


def chat_enabled_for(session: Session, user_id: Optional[int], device_id: Optional[str]) -> bool:
    """สวิตช์เปิด + อยู่ในกลุ่ม rollout (คนเดิมได้ผลเดิมเสมอเพราะใช้ hash)"""
    if not get(session, "chat_enabled"):
        return False
    return chat_bucket(user_id, device_id) < get(session, "chat_rollout_percent")


if __name__ == "__main__":
    from app.database import create_db_and_tables, engine

    create_db_and_tables()
    args = sys.argv[1:]
    with Session(engine) as s:
        if args[:1] == ["set"] and len(args) == 3:
            set_value(s, args[1], args[2])
        elif args[:1] == ["unset"] and len(args) == 2:
            set_value(s, args[1], None)
        elif args[:1] != ["get"]:
            print(__doc__)
            sys.exit(1)
        for k in KNOWN:
            print(f"{k} = {get(s, k)}")
