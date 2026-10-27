from django.urls import path

from .api import MileageView, MotorcycleDetailView, MotorcycleListView, OwnerView

urlpatterns = [
    path("motorcycles/", MotorcycleListView.as_view(), name="motorcycle-list"),
    path("motorcycles/<int:pk>/", MotorcycleDetailView.as_view(), name="motorcycle-detail"),
    path("motorcycles/<int:pk>/mileage/", MileageView.as_view(), name="motorcycle-mileage"),
    path("motorcycles/<int:pk>/owner/", OwnerView.as_view(), name="motorcycle-owner"),
]
