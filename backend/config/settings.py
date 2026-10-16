"""Configuración de Django. Los valores sensibles vienen de variables de entorno.

Desarrollo: sin variables (DEBUG, SQLite). Producción: ver .env.example y docs/despliegue.md.
"""
import os
import re
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
_DEV_SECRET = "solo-para-desarrollo-no-usar-en-produccion"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_SECRET)
if not DEBUG and SECRET_KEY == _DEV_SECRET:
    raise ImproperlyConfigured("En producción hay que definir DJANGO_SECRET_KEY.")
# localhost siempre: el healthcheck del contenedor se llama a sí mismo por 127.0.0.1.
ALLOWED_HOSTS = [*env_list("DJANGO_ALLOWED_HOSTS"), "localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.sales",
    "apps.cash",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Sirve el frontend compilado y los estáticos del admin desde el mismo proceso (mismo dominio).
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL en producción (DB_ENGINE=postgres); SQLite para desarrollo y tests.
if os.environ.get("DB_ENGINE") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "inventario"),
            "USER": os.environ.get("DB_USER", "inventario"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        # Sesión iniciada y sin contraseña temporal pendiente (spec 003).
        "apps.accounts.drf.IsAuthenticatedAndReady",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("LOGIN_RATE", "5/min"),
    },
}

# Sesión en cookie HttpOnly: la PWA y la API se sirven desde el mismo dominio.
# Dura un turno largo; sin conexión la caja sigue vendiendo y, al volver, se inicia sesión de nuevo.
SESSION_COOKIE_AGE = int(os.environ.get("SESSION_COOKIE_AGE", 12 * 60 * 60))
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Cookies solo por HTTPS en producción. DJANGO_SECURE_COOKIES=0 únicamente para probar sin HTTPS.
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = os.environ.get(
    "DJANGO_SECURE_COOKIES", "0" if DEBUG else "1"
) == "1"
# Detrás de un proxy que termina HTTPS (Caddy, nginx, Cloudflare): confiar en X-Forwarded-Proto.
if os.environ.get("DJANGO_BEHIND_HTTPS_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# En producción la PWA y la API comparten dominio y no hace falta. En desarrollo la PWA corre
# en el servidor de Vite (5173 con "npm run dev", 4173 con "vite preview"), que reenvía /api a Django.
_dev_origins = (
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173" if DEBUG else ""
)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", _dev_origins)

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# En la imagen de Docker los estáticos se recopilan con nombres con hash (STATIC_MANIFEST=1);
# en desarrollo y tests se sirven tal cual.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if os.environ.get("STATIC_MANIFEST") == "1"
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# El build del frontend (frontend/dist) se sirve en la raíz: "/" → index.html, /assets/…, /sw.js.
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", BASE_DIR.parent / "frontend" / "dist"))
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST
    WHITENOISE_INDEX_FILE = True
# Los archivos de /assets llevan hash en el nombre: se pueden guardar en caché para siempre.
# index.html y sw.js no, para que las versiones nuevas lleguen.
_HASHED_ASSET = re.compile(r"^/assets/.+-[A-Za-z0-9_-]{8,}\.\w+$")
WHITENOISE_IMMUTABLE_FILE_TEST = lambda path, url: bool(_HASHED_ASSET.match(url))  # noqa: E731

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
