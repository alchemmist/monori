# Stage 1: build the web app and the docs site
FROM node:22-alpine AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --silent
COPY web/ ./
RUN npm run build

WORKDIR /build/web-docs
COPY web-docs/package.json web-docs/package-lock.json ./
RUN npm ci --silent
COPY web-docs/ ./
COPY docs/ /build/docs/
RUN npm run build

# Stage 2: python server
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"
COPY server/app ./app
COPY --from=web /build/web/dist ./static
COPY --from=web /build/web-docs/dist ./docs-static
ENV MONORI_DB=/app/data/monori.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
