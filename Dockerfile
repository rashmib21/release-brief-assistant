# Stage 1: build the React app
FROM node:22-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# Stage 2: FastAPI serves the API and the built React app from one service
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY --from=frontend /fe/dist ./frontend/dist
WORKDIR /app/backend
ENV FRONTEND_DIST=../frontend/dist
EXPOSE 8000
# --proxy-headers: behind Render's proxy, use the real client IP (the rate limit is per IP)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
