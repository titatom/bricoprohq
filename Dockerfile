FROM node:20-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline
COPY frontend ./
ENV NODE_ENV=production
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV NODE_ENV=production \
    DATA_DIR=/data \
    DATABASE_URL=sqlite+pysqlite:////data/bricoprohq.db \
    API_URL=http://127.0.0.1:8000 \
    NEXT_TELEMETRY_DISABLED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/app /app/backend/app
COPY backend/migrations /app/backend/migrations
COPY backend/alembic.ini /app/backend/alembic.ini

COPY frontend/package.json frontend/package-lock.json* /app/frontend/
RUN cd /app/frontend && npm ci --omit=dev --prefer-offline
COPY --from=frontend-build /app/frontend/.next /app/frontend/.next
COPY --from=frontend-build /app/frontend/public /app/frontend/public
COPY --from=frontend-build /app/frontend/next.config.js /app/frontend/next.config.js

COPY docker/entrypoint.sh /usr/local/bin/bricoprohq-entrypoint
RUN chmod +x /usr/local/bin/bricoprohq-entrypoint \
    && mkdir -p /data/logos

EXPOSE 3000
VOLUME ["/data"]
CMD ["bricoprohq-entrypoint"]
