FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY frontend ./frontend

# บริการ hosting (Render/Railway) กำหนดพอร์ตมาให้ผ่านตัวแปร PORT
# ต้องฟังพอร์ตนั้น ไม่งั้นบริการจะมองว่าแอปไม่ตอบสนองแล้ว deploy ล้มเหลว
ENV PORT=8000
EXPOSE 8000

# ใช้ shell form เพื่อให้ $PORT ถูกแทนค่าตอนรัน (exec form จะส่งเป็นข้อความดิบ)
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
