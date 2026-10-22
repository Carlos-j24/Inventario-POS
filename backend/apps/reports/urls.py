from django.urls import path

from .views import (
    InventoryReportView, MarginsReportView, ProductsReportView, QuotesReportView, SalesReportView, ShiftsReportView,
)

urlpatterns = [
    path("sales/", SalesReportView.as_view(), name="report-sales"),
    path("products/", ProductsReportView.as_view(), name="report-products"),
    path("inventory/", InventoryReportView.as_view(), name="report-inventory"),
    path("margins/", MarginsReportView.as_view(), name="report-margins"),
    path("shifts/", ShiftsReportView.as_view(), name="report-shifts"),
    path("quotes/", QuotesReportView.as_view(), name="report-quotes"),
]
