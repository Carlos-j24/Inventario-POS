from rest_framework import generics

from apps.accounts.drf import require_any

from .models import NumberingResolution
from .serializers import NumberingResolutionSerializer


class NumberingListView(generics.ListAPIView):
    """Resoluciones de numeración activas con sus avisos (?register=). Se cargan en el admin."""

    serializer_class = NumberingResolutionSerializer
    permission_classes = [require_any("cash.operate", "reports.view")]
    pagination_class = None

    def get_queryset(self):
        resolutions = NumberingResolution.objects.filter(is_active=True).select_related("register")
        register = self.request.query_params.get("register")
        return resolutions.filter(register_id=register) if register else resolutions
