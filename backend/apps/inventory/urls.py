from django.urls import path

from .adjustment_api import AdjustmentApproveView, AdjustmentDetailView, AdjustmentListView, AdjustmentRejectView
from .views import KardexView, ReceiptView, StockLevelListView, WarehouseListView

urlpatterns = [
    path("warehouses/", WarehouseListView.as_view(), name="warehouse-list"),
    path("receipts/", ReceiptView.as_view(), name="receipt-create"),
    path("stock/", StockLevelListView.as_view(), name="stock-list"),
    path("kardex/<int:product_id>/", KardexView.as_view(), name="kardex"),
    # Ajustes (spec 006, T3)
    path("adjustments/", AdjustmentListView.as_view(), name="adjustment-list"),
    path("adjustments/<int:pk>/", AdjustmentDetailView.as_view(), name="adjustment-detail"),
    path("adjustments/<int:pk>/approve/", AdjustmentApproveView.as_view(), name="adjustment-approve"),
    path("adjustments/<int:pk>/reject/", AdjustmentRejectView.as_view(), name="adjustment-reject"),
]
