from django.urls import path

from .views import SaleCreateView, SaleDetailView

urlpatterns = [
    path("", SaleCreateView.as_view(), name="sale-create"),
    path("<int:pk>/", SaleDetailView.as_view(), name="sale-detail"),
]
