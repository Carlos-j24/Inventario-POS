from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.drf import require

from .period import parse_period
from .services import products_report, sales_report


class SalesReportView(APIView):
    """Ventas del período: totales, por día, caja, vendedor y medio de pago (?from, ?to, ?register, ?salesperson)."""

    permission_classes = [require("reports.view")]

    def get(self, request):
        start, end = parse_period(request.query_params)
        q = request.query_params
        return Response(sales_report(start, end, register=q.get("register"), salesperson=q.get("salesperson")))


class ProductsReportView(APIView):
    """Productos más vendidos (por cantidad y por valor) y sin movimiento (?from, ?to, ?register, ?limit)."""

    permission_classes = [require("reports.view")]

    def get(self, request):
        start, end = parse_period(request.query_params)
        try:
            limit = max(1, min(int(request.query_params.get("limit", 20)), 200))
        except ValueError:
            limit = 20
        return Response(products_report(start, end, register=request.query_params.get("register"), limit=limit))
