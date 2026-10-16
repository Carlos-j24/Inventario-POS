from django.urls import path

from .views import ShiftCloseView, ShiftDetailView, ShiftOpenView

urlpatterns = [
    path("shifts/", ShiftOpenView.as_view(), name="shift-open"),
    path("shifts/<int:pk>/", ShiftDetailView.as_view(), name="shift-detail"),
    path("shifts/<int:pk>/close/", ShiftCloseView.as_view(), name="shift-close"),
]
