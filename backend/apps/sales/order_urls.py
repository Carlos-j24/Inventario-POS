from django.urls import path

from .order_views import OrderByCodeView, OrderCancelView, OrderListCreateView

urlpatterns = [
    path("", OrderListCreateView.as_view(), name="order-list"),
    path("code/<int:code>/", OrderByCodeView.as_view(), name="order-by-code"),
    path("<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
]
