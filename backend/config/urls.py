from django.contrib import admin
from django.urls import include, path

from apps.accounts.urls import auth_urlpatterns

from .health import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/auth/", include(auth_urlpatterns)),
    path("api/accounts/", include("apps.accounts.urls")),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/sales/", include("apps.sales.urls")),
    path("api/orders/", include("apps.sales.order_urls")),
    path("api/cash/", include("apps.cash.urls")),
    path("api/reports/", include("apps.reports.urls")),
]
