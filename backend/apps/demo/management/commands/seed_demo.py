"""manage.py seed_demo: llena una base de desarrollo con datos para mostrar la app.

    python manage.py seed_demo              # base recién migrada y vacía
    python manage.py seed_demo --fresh      # borra la base SQLite, la vuelve a crear y la llena
    python manage.py seed_demo --password X # la misma contraseña para todos (si no, una al azar por usuario)
    python manage.py seed_demo --taller     # un taller de motos con el módulo de taller (spec 009) en vez de la ferretería

Solo con DEBUG: nunca en producción. Las contraseñas se muestran una vez y no se guardan.
"""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.demo.seed import seed


class Command(BaseCommand):
    help = "Llena una base de desarrollo con datos de demostración (solo con DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument("--fresh", action="store_true", help="Borra la base SQLite y la crea de nuevo antes de llenarla.")
        parser.add_argument("--password", help="Contraseña para todos los usuarios de demostración.")
        parser.add_argument("--taller", action="store_true", help="Un taller de motos (módulo de taller, clientes y motos).")

    def handle(self, *args, fresh=False, password=None, taller=False, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo solo corre con DEBUG: nunca en producción.")
        if password is not None and len(password) < 8:
            raise CommandError("La contraseña debe tener al menos 8 caracteres.")
        if fresh:
            self._recreate()
        try:
            passwords = seed(password=password, workshop=taller)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS("Datos de demostración listos. Usuarios (guarda las contraseñas: no se guardan en ningún lado):"))
        for username, secret in passwords.items():
            self.stdout.write(f"  {username:<16} {secret}")

    def _recreate(self):
        if connection.vendor != "sqlite":
            raise CommandError("--fresh solo borra bases SQLite de desarrollo.")
        name = Path(settings.DATABASES["default"]["NAME"])
        connection.close()
        try:
            name.unlink(missing_ok=True)
        except PermissionError as exc:
            raise CommandError(f"No se pudo borrar {name.name}: cierra el servidor (runserver) y vuelve a intentar.") from exc
        call_command("migrate", verbosity=0)
