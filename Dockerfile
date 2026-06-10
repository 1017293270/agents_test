FROM node:22-bookworm-slim AS frontend

WORKDIR /app
COPY package.json package-lock.json* tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm install
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    APP_DATA_DIR=/app/data \
    EXPORT_DIR=/app/exports \
    CLAUDE_BIN=claude \
    CLAUDE_TIMEOUT_SECONDS=180

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY backend ./backend
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
