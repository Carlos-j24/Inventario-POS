from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from .models import Sale
from .serializers import SaleInputSerializer, SaleSerializer
from .services import create_sale


class SaleCreateView(APIView):
    """Registra una venta. Reenviar el mismo client_uuid devuelve la venta ya creada (200)."""

    permission_classes = [require("sales.create")]

    def post(self, request):
        data = SaleInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            sale, created = create_sale(user=request.user, **data.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(
            SaleSerializer(sale).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SaleDetailView(generics.RetrieveAPIView):
    permission_classes = [require("sales.create")]
    serializer_class = SaleSerializer
    queryset = Sale.objects.select_related("warehouse", "seller").prefetch_related(
        "lines__product", "lines__unit"
    )
