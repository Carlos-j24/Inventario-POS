from django.urls import path

from .api import MileageView, MotorcycleDetailView, MotorcycleListView, OwnerView
from .maintenance_api import PlanDetailView, PlanListView, ReminderActionView, ReminderListView
from .order_api import (
    LineActionView, LineDetailView, LineListView, MechanicListView, OrderActionView, OrderDetailView, OrderListView,
)

urlpatterns = [
    path("motorcycles/", MotorcycleListView.as_view(), name="motorcycle-list"),
    path("motorcycles/<int:pk>/", MotorcycleDetailView.as_view(), name="motorcycle-detail"),
    path("motorcycles/<int:pk>/mileage/", MileageView.as_view(), name="motorcycle-mileage"),
    path("motorcycles/<int:pk>/owner/", OwnerView.as_view(), name="motorcycle-owner"),
    path("orders/", OrderListView.as_view(), name="work-order-list"),
    path("orders/mechanics/", MechanicListView.as_view(), name="work-order-mechanics"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="work-order-detail"),
    path("orders/<int:pk>/lines/", LineListView.as_view(), name="work-order-lines"),
    path("orders/<int:pk>/lines/<int:line_id>/", LineDetailView.as_view(), name="work-order-line"),
    path("orders/<int:pk>/lines/<int:line_id>/<str:action>/", LineActionView.as_view(), name="work-order-line-action"),
    path("orders/<int:pk>/<str:action>/", OrderActionView.as_view(), name="work-order-action"),
    path("plans/", PlanListView.as_view(), name="maintenance-plan-list"),
    path("plans/<int:pk>/", PlanDetailView.as_view(), name="maintenance-plan-detail"),
    path("maintenance/", ReminderListView.as_view(), name="maintenance-list"),
    path("maintenance/<int:pk>/<str:action>/", ReminderActionView.as_view(), name="maintenance-action"),
]
