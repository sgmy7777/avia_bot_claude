FROM python:3.11-slim

WORKDIR /app

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Код
COPY app/ ./app/

# Директория для БД (монтировать как volume)
RUN mkdir -p /app/data

# Health-check: проверяем что воркер обновлял файл не более 15 минут назад (fix #5)
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "\
import os, time, sys; \
p='/tmp/avia_bot_health'; \
sys.exit(0 if os.path.exists(p) and time.time() - os.path.getmtime(p) < 900 else 1)"

CMD ["python3", "-m", "app.main"]
