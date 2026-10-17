from django.conf import settings
from django.core.management.base import BaseCommand

from apps.invoicing.queue import process_queue


class Command(BaseCommand):
    help = "Envía a la DIAN los documentos electrónicos pendientes (programarlo cada minuto)."

    def handle(self, *args, **options):
        if not settings.INVOICING_ENABLED:
            self.stdout.write("Facturación electrónica apagada (INVOICING_ENABLED=0): nada que enviar.")
            return
        counts = process_queue()
        self.stdout.write(
            f"Validados: {counts['validated']} · rechazados: {counts['rejected']} · sin respuesta: {counts['unavailable']}"
        )
