from django.urls import path

from .views import KardexView, ReceiptView, StockLevelListView, WarehouseListView

urlpatterns = [
    path("warehouses/", WarehouseListView.as_view(), name="warehouse-list"),
    path("receipts/", ReceiptView.as_view(), name="receipt-create"),
    path("stock/", StockLevelListView.as_view(), name="stock-list"),
    path("kardex/<int:product_id>/", KardexView.as_view(), name="kardex"),
]
