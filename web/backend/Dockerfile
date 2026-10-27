FROM node:22-alpine AS frontend
WORKDIR /app/web/frontend
ARG VITE_ENTRA_CLIENT_ID
ARG VITE_ENTRA_AUTHORITY
ARG VITE_ENTRA_REDIRECT_URI
ARG VITE_ENTRA_API_SCOPE
ARG VITE_BACKEND_BASE_URL=
ENV VITE_ENTRA_CLIENT_ID=${VITE_ENTRA_CLIENT_ID}
ENV VITE_ENTRA_AUTHORITY=${VITE_ENTRA_AUTHORITY}
ENV VITE_ENTRA_REDIRECT_URI=${VITE_ENTRA_REDIRECT_URI}
ENV VITE_ENTRA_API_SCOPE=${VITE_ENTRA_API_SCOPE}
ENV VITE_BACKEND_BASE_URL=${VITE_BACKEND_BASE_URL}
COPY web/frontend/package.json web/frontend/package-lock.json ./
RUN npm ci
COPY web/frontend/src/ ./src/
COPY web/frontend/public/ ./public/
COPY web/frontend/index.html web/frontend/redirect.html web/frontend/tsconfig*.json web/frontend/vite.config.ts ./
RUN test -n "${VITE_ENTRA_CLIENT_ID}" \
    && test -n "${VITE_ENTRA_AUTHORITY}" \
    && test -n "${VITE_ENTRA_REDIRECT_URI}" \
    && test -n "${VITE_ENTRA_API_SCOPE}" \
    && npm run build

FROM python:3.13-slim
WORKDIR /app
ARG PYTHON_PACKAGE_INDEX_URL=https://packagefeedproxy.microsoft.io/pypi/simple/
COPY web/backend/ ./web/backend/
COPY --from=frontend /app/web/frontend/dist ./web/frontend/dist
RUN pip install --no-cache-dir --index-url "${PYTHON_PACKAGE_INDEX_URL}" ./web/backend
ENV PORT=8080 \
    VOICE_FRONTEND_DIST=/app/web/frontend/dist
EXPOSE 8080
CMD ["python", "-m", "hotel_voice_proxy.app"]
