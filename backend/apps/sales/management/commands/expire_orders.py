from django.core.management.base import BaseCommand

from apps.sales.orders import expire_orders


class Command(BaseCommand):
    help = "Marca como vencidos los pedidos pendientes de días anteriores (programarlo a diario, p. ej. a las 00:05)."

    def handle(self, *args, **options):
        self.stdout.write(f"Pedidos vencidos: {expire_orders()}")
