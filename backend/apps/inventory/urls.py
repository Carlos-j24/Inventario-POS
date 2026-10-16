from django.urls import path

from .views import KardexView, ReceiptView, StockLevelListView

urlpatterns = [
    path("receipts/", ReceiptView.as_view(), name="receipt-create"),
    path("stock/", StockLevelListView.as_view(), name="stock-list"),
    path("kardex/<int:product_id>/", KardexView.as_view(), name="kardex"),
]
