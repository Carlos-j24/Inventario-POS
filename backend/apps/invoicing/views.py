from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require, require_any

from .models import FiscalDocument, NumberingResolution
from .queue import DEADLINE, DUE_SOON, retry
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
