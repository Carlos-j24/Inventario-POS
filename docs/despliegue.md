# Despliegue

Un solo contenedor con Django (gunicorn) que también sirve el frontend compilado (WhiteNoise), más PostgreSQL. Así la PWA y la API comparten dominio, que es lo que exige la sesión en cookie con CSRF.

```
Navegador ──HTTPS──▶ Proxy (Caddy / nginx / Cloudflare) ──HTTP──▶ app:8000 ──▶ db (PostgreSQL)
                                                                   ├─ /          frontend (index.html, /assets, /sw.js)
                                                                   ├─ /api/…     Django REST
                                                                   ├─ /admin/…   admin de Django
                                                                   └─ /static/…  estáticos del admin
```

## Requisitos
- Un servidor con Docker y Docker Compose.
- Un dominio con **HTTPS**. Sin HTTPS, el navegador no registra el service worker (no hay modo sin conexión) y las cookies seguras no viajan. La excepción es `localhost`.

## Primera vez

```bash
git clone https://github.com/Carlos-j24/Inventario-POS.git
cd Inventario-POS
cp .env.example .env
```

Edita `.env`: `DJANGO_SECRET_KEY`, `DB_PASSWORD`, `DJANGO_ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` con tu dominio. Para generar una clave:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

Levanta todo (las migraciones se aplican solas al arrancar):

```bash
docker compose up -d --build
```

Crea el primer administrador:

```bash
docker compose exec app python manage.py createsuperuser
```

Entra a `https://tu-dominio/admin/`. Crea al menos una **bodega**, una **caja** y los productos, y asigna roles a los usuarios. La app queda en `https://tu-dominio/`.

## HTTPS con Caddy (ejemplo)
Caddy obtiene y renueva el certificado solo. En el mismo servidor, un `Caddyfile`:

```
pos.mi-ferreteria.com {
    reverse_proxy localhost:8000
}
```

Y en `.env`: `DJANGO_BEHIND_HTTPS_PROXY=1` y `DJANGO_SECURE_COOKIES=1`.

## Actualizar a una versión nueva

```bash
git pull
docker compose up -d --build
```

Los navegadores reciben la versión nueva del frontend al recargar: `index.html` y `sw.js` no se guardan en caché por mucho tiempo, y los archivos de `/assets` llevan hash en el nombre.

## Copias de seguridad
La base de datos vive en el volumen `pgdata`. Copia diaria recomendada:

```bash
docker compose exec -T db pg_dump -U inventario inventario | gzip > respaldo-$(date +%F).sql.gz
```

Restaurar (en una base vacía):

```bash
gunzip -c respaldo-AAAA-MM-DD.sql.gz | docker compose exec -T db psql -U inventario inventario
```

## Comprobar que está bien
- `https://tu-dominio/api/health/` responde `{"status": "ok", "database": true}`. Docker lo usa como healthcheck.
- `scripts/smoke-test.sh` levanta todo en local y prueba el frontend, el admin y el inicio de sesión. El CI lo ejecuta en cada PR.

## Variables de entorno

| Variable | Para qué | Por defecto |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta (obligatoria en producción) | — |
| `DJANGO_ALLOWED_HOSTS` | Dominios permitidos, separados por coma | `localhost` |
| `CSRF_TRUSTED_ORIGINS` | Orígenes con `https://` | — |
| `DJANGO_BEHIND_HTTPS_PROXY` | `1` si un proxy termina HTTPS | `0` |
| `DJANGO_SECURE_COOKIES` | Cookies solo por HTTPS | `1` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL | `inventario`, `inventario`, — |
| `APP_PORT` | Puerto publicado | `8000` |
| `GUNICORN_WORKERS` | Procesos de gunicorn | `3` |
| `SESSION_COOKIE_AGE` | Duración de la sesión en segundos | `43200` (12 h) |
| `LOGIN_RATE` | Intentos de inicio de sesión | `5/min` |
