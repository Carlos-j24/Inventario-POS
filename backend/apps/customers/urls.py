from django.urls import path

from .views import CustomerDetailView, CustomerListCreateView, FinalConsumerView

urlpatterns = [
    path("", CustomerListCreateView.as_view(), name="customer-list"),
    path("final-consumer/", FinalConsumerView.as_view(), name="customer-final-consumer"),
    path("<int:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
]
