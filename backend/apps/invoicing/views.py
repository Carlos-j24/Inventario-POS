from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any
from apps.cash.models import CashRegister
from apps.sales.models import Sale

from .models import ContingencyBlock, FiscalDocument, NumberingResolution
from .numbering import NumberingError, take_numbers
from .documents import send_document
from .queue import DEADLINE, DUE_SOON, backoff, retry
from .ticket import business_data, ticket_for_sale
from .serializers import FiscalDocumentDetailSerializer, FiscalDocumentRowSerializer, NumberingResolutionSerializer

Status = FiscalDocument.Status


class NumberingListView(generics.ListAPIView):
    """Resoluciones de numeración activas con sus avisos (?register=). Se cargan en el admin."""

    serializer_class = NumberingResolutionSerializer
    permission_classes = [require_any("cash.operate", "reports.view")]
    pagination_class = None

    def get_queryset(self):
        resolutions = NumberingResolution.objects.filter(is_active=True).select_related("register")
        register = self.request.query_params.get("register")
        return resolutions.filter(register_id=register) if register else resolutions


def documents():
    return FiscalDocument.objects.select_related("sale__shift__register", "customer", "corrects")


class FiscalDocumentListView(APIView):
    """Bandeja del supervisor (spec 005, T4): por defecto lo que no está validado.

    ?status=PENDING|REJECTED|VALIDATED filtra. Trae un resumen con pendientes, rechazados y los
    pendientes que pasaron o están por pasar el plazo de 48 horas. Máximo 200, los más recientes.
    """

    permission_classes = [require("reports.view")]

    def get(self, request):
        now = timezone.now()
        pending = FiscalDocument.objects.filter(status=Status.PENDING)
        summary = {
            "pending": pending.count(),
            "rejected": FiscalDocument.objects.filter(status=Status.REJECTED).count(),
            "overdue": pending.filter(issued_at__lt=now - DEADLINE).count(),
            "due_soon": pending.filter(issued_at__gte=now - DEADLINE, issued_at__lte=now - DEADLINE + DUE_SOON).count(),
        }
        wanted = request.query_params.get("status")
        rows = documents().filter(status=wanted) if wanted in Status.values else documents().filter(~Q(status=Status.VALIDATED))
        data = FiscalDocumentRowSerializer(rows.order_by("-issued_at", "-pk")[:200], many=True).data
        return Response({"summary": summary, "results": data})


class FiscalDocumentDetailView(generics.RetrieveAPIView):
    serializer_class = FiscalDocumentDetailSerializer
    permission_classes = [require("reports.view")]

    def get_queryset(self):
        return documents().prefetch_related("events")


class FiscalDocumentRetryView(APIView):
    """Vuelve a poner en la cola un documento rechazado (tras corregir, p. ej., los datos del cliente)."""

    permission_classes = [require("sales.void")]

    def post(self, request, pk):
        document = get_object_or_404(FiscalDocument, pk=pk)
        try:
            retry(document, request.user)
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(FiscalDocumentDetailSerializer(documents().prefetch_related("events").get(pk=pk)).data)


class InvoicingStatusView(APIView):
    """Si la facturación electrónica está encendida: el POS solo reserva bloques si lo está."""

    permission_classes = [require_any("cash.operate", "sales.create", "reports.view")]

    def get(self, request):
        return Response({"enabled": settings.INVOICING_ENABLED})


class ContingencyBlockView(APIView):
    """Reserva un bloque de números de contingencia para que un equipo de caja venda sin servidor (T5)."""

    permission_classes = [require("cash.operate")]

    def post(self, request):
        if not settings.INVOICING_ENABLED:
            return Response({"detail": "La facturación electrónica está apagada."}, status=status.HTTP_409_CONFLICT)
        register = get_object_or_404(CashRegister, pk=request.data.get("register"))
        try:
            with transaction.atomic():
                resolution, first, last = take_numbers(
                    register, NumberingResolution.DocumentType.CONTINGENCY, settings.CONTINGENCY_BLOCK_SIZE,
                )
                ContingencyBlock.objects.create(
                    register=register, resolution=resolution, start=first, end=last, reserved_by=request.user,
                )
        except NumberingError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"register": register.pk, "prefix": resolution.prefix, "start": first, "end": last},
                        status=status.HTTP_201_CREATED)


class BusinessView(APIView):
    """Datos del negocio para el encabezado del tiquete (el POS los guarda para imprimir sin conexión)."""

    def get(self, request):
        return Response(business_data())


class TicketView(APIView):
    """Datos del tiquete de 80 mm de una venta (art. 19), con el QR si la DIAN ya validó."""

    permission_classes = [require_any("cash.operate", "sales.void", "reports.view")]

    def get(self, request, sale_id):
        sale = get_object_or_404(Sale.objects.select_related("shift__register", "seller"), pk=sale_id)
        return Response(ticket_for_sale(sale))


class FiscalDocumentSendView(APIView):
    """La caja lo envía apenas cobra, para entregar el tiquete ya validado sin esperar a la cola."""

    permission_classes = [require("cash.operate")]

    def post(self, request, pk):
        document = send_document(get_object_or_404(FiscalDocument, pk=pk))
        if document.status == Status.PENDING and document.last_error:
            # Sin respuesta: la cola reintenta con su espera creciente.
            document.next_attempt_at = timezone.now() + backoff(document.attempts)
            document.save(update_fields=["next_attempt_at"])
        return Response({"status": document.status, "last_error": document.last_error})
