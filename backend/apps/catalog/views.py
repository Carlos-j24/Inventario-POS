from django.db.models import Prefetch
from rest_framework import generics

from .models import Product, ProductUnit
from .serializers import ProductSerializer


class ProductListView(generics.ListAPIView):
    """Catálogo para el POS: el frontend lo guarda en el navegador para vender sin conexión."""

    serializer_class = ProductSerializer
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("category", "base_unit")
        # Las presentaciones desactivadas (spec 006) ya no se ofrecen en la caja.
        .prefetch_related(Prefetch("units", queryset=ProductUnit.objects.filter(is_active=True).select_related("unit")))
    )
