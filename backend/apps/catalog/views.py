from rest_framework import generics

from .models import Product
from .serializers import ProductSerializer


class ProductListView(generics.ListAPIView):
    """Catálogo para el POS: el frontend lo guarda en el navegador para vender sin conexión."""

    serializer_class = ProductSerializer
    queryset = (
        Product.objects.filter(is_active=True)
        .select_related("category", "base_unit")
        .prefetch_related("units__unit")
    )
