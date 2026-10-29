"""Marca de cada instalación: el logo y los íconos del negocio, fuera del repositorio.

`BRAND_DIR` apunta a una carpeta con `logo.png` (barra superior, ingreso y hojas impresas) y, si se
quiere instalar la app con el ícono del negocio, `icon-192.png` e `icon-512.png`. Sin la carpeta, o
sin algún archivo, la app queda como siempre: sin logo y con el ícono genérico. Todo es público
porque la pantalla de ingreso y el ícono se ven antes de entrar.
"""
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse

FILES = ("logo.png", "icon-192.png", "icon-512.png")
MAX_AGE = 3600  # el service worker los pide primero a la red: un logo nuevo llega a más tardar en una hora

MANIFEST = {
    "name": "Inventario POS",
    "short_name": "POS",
    "description": "Caja, inventario y taller del negocio.",
    "lang": "es-CO",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#f3f5f8",
    "theme_color": "#1f4e79",
}
GENERIC_ICONS = [
    {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
    {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
]


def brand_path(name):
    """El archivo de la marca, o None si la instalación no lo trae."""
    if not settings.BRAND_DIR or name not in FILES:
        return None
    path = settings.BRAND_DIR / name
    return path if path.is_file() else None


def brand_file(request, name):
    path = brand_path(name)
    if path is None:
        raise Http404("Esta instalación no tiene ese archivo de marca.")
    response = FileResponse(path.open("rb"))  # image/png por el nombre
    response["Cache-Control"] = f"public, max-age={MAX_AGE}"
    return response


def manifest(request):
    """El manifiesto de la PWA, con los íconos del negocio si la instalación los trae."""
    icons = [
        {"src": f"/brand/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png", "purpose": "any"}
        for size in (192, 512) if brand_path(f"icon-{size}.png")
    ]
    response = JsonResponse({**MANIFEST, "icons": icons or GENERIC_ICONS}, content_type="application/manifest+json")
    response["Cache-Control"] = f"public, max-age={MAX_AGE}"
    return response
