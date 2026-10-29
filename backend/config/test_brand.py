"""Logo e íconos de cada instalación (config/brand.py)."""
import pytest
from django.test import Client

PNG = b"\x89PNG\r\n\x1a\nlogo"


@pytest.fixture
def brand(tmp_path, settings):
    settings.BRAND_DIR = tmp_path
    return tmp_path


@pytest.fixture
def anonymous():
    return Client()  # la pantalla de ingreso y el ícono se ven antes de entrar


def test_without_a_brand_folder_there_is_no_logo(anonymous, settings):
    settings.BRAND_DIR = None
    assert anonymous.get("/brand/logo.png").status_code == 404


def test_the_logo_of_the_installation(anonymous, brand):
    (brand / "logo.png").write_bytes(PNG)
    response = anonymous.get("/brand/logo.png")
    assert (response.status_code, response["Content-Type"], response["Cache-Control"]) == (200, "image/png", "public, max-age=3600")
    assert b"".join(response.streaming_content) == PNG


@pytest.mark.parametrize("name", ["icon-64.png", "secreto.txt", "..%2Fsettings.py", "logo.PNG"])
def test_only_the_brand_files_are_served(anonymous, brand, name):
    (brand / "secreto.txt").write_text("no")
    (brand / "icon-64.png").write_bytes(PNG)
    assert anonymous.get(f"/brand/{name}").status_code == 404


def test_a_missing_file_is_404_even_with_the_folder(anonymous, brand):
    assert anonymous.get("/brand/icon-192.png").status_code == 404


def test_the_manifest_uses_the_generic_icon_without_brand(anonymous, settings):
    settings.BRAND_DIR = None
    response = anonymous.get("/brand/manifest.webmanifest")
    data = response.json()
    assert (response.status_code, response["Content-Type"]) == (200, "application/manifest+json")
    assert (data["name"], data["start_url"], data["display"]) == ("Inventario POS", "/", "standalone")
    assert [(i["src"], i["purpose"]) for i in data["icons"]] == [("/icon.svg", "any"), ("/icon.svg", "maskable")]


def test_the_manifest_uses_the_icons_of_the_installation(anonymous, brand):
    (brand / "icon-192.png").write_bytes(PNG)
    (brand / "icon-512.png").write_bytes(PNG)
    icons = anonymous.get("/brand/manifest.webmanifest").json()["icons"]
    assert icons == [
        {"src": "/brand/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/brand/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    ]
    assert anonymous.get("/brand/icon-512.png").status_code == 200


def test_only_the_icons_it_has(anonymous, brand):
    (brand / "icon-512.png").write_bytes(PNG)
    assert [i["src"] for i in anonymous.get("/brand/manifest.webmanifest").json()["icons"]] == ["/brand/icon-512.png"]
