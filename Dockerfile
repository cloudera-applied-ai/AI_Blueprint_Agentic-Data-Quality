# Stage 1 — build the React frontend
FROM node:22-alpine AS frontend
WORKDIR /build
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend/ ./
RUN npm run build

# Stage 2 — Python runtime serving the API and the built frontend
FROM python:3.12-slim
WORKDIR /app
COPY app/backend/requirements.txt app/backend/requirements.txt
RUN pip install --no-cache-dir -r app/backend/requirements.txt
COPY app/backend/ app/backend/
# app.py serves ../frontend/dist as static files when it exists
COPY --from=frontend /build/dist app/frontend/dist
WORKDIR /app/app/backend
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
