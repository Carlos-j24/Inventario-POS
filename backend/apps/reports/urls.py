from django.urls import path

from .views import ProductsReportView, SalesReportView

urlpatterns = [
    path("sales/", SalesReportView.as_view(), name="report-sales"),
    path("products/", ProductsReportView.as_view(), name="report-products"),
]
