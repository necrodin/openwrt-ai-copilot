FROM python:3.12-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY database ./database
COPY ai ./ai
COPY providers ./providers
COPY rag ./rag
COPY vision ./vision
COPY router-agent ./router-agent
COPY backend ./backend

RUN pip install --no-cache-dir ./database ./ai ./providers ./rag ./vision ./router-agent ./backend

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL="sqlite:////data/openwrt_ai.db"
WORKDIR /app

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=build /app/backend/app ./app

RUN groupadd --system --gid 1000 openwrta \
    && useradd --system --uid 1000 --gid openwrta openwrta \
    && mkdir -p /data \
    && chown openwrta:openwrta /data

USER openwrta
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
