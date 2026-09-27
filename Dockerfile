FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade 'pip>=26.2,<27' \
    && pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT} --log-level info"]
