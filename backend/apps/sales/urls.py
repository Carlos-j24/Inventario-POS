from django.urls import path

from .views import SaleCreateView, SaleDetailView, SaleReturnView, SaleVoidView

urlpatterns = [
    path("", SaleCreateView.as_view(), name="sale-create"),
    path("<int:pk>/", SaleDetailView.as_view(), name="sale-detail"),
    path("<int:pk>/void/", SaleVoidView.as_view(), name="sale-void"),
    path("<int:pk>/returns/", SaleReturnView.as_view(), name="sale-return"),
]
