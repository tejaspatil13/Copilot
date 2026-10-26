# ---- build the dashboard ----
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UKA_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
 && python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs')"
COPY backend/ backend/
COPY templates/ templates/
COPY --from=frontend /frontend/dist frontend/dist
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# One worker: jobs run in-process and share state through SQLite.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
