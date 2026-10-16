from django.urls import path

from .views import CashRegisterListView, ShiftCloseView, ShiftDetailView, ShiftOpenView

urlpatterns = [
    path("registers/", CashRegisterListView.as_view(), name="register-list"),
    path("shifts/", ShiftOpenView.as_view(), name="shift-open"),
    path("shifts/<int:pk>/", ShiftDetailView.as_view(), name="shift-detail"),
    path("shifts/<int:pk>/close/", ShiftCloseView.as_view(), name="shift-close"),
]
