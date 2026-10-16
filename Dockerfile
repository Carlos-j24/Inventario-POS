# Imagen de producción: un solo contenedor con Django (gunicorn) que sirve también el frontend
# compilado (WhiteNoise), así la PWA y la API comparten dominio (sesión en cookie + CSRF).

# --- 1. Compilar el frontend ---------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

# --- 2. Backend ------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=0 \
    STATIC_MANIFEST=1 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend/dist
# collectstatic no toca la base de datos; la clave solo hace falta para cargar la configuración.
RUN DJANGO_SECRET_KEY=solo-para-collectstatic python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/').status == 200 else 1)"

# Aplica las migraciones al arrancar y levanta gunicorn.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 60 --access-logfile -"]
