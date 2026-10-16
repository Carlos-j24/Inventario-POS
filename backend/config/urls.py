from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/catalog/", include("apps.catalog.urls")),
    path("api/inventory/", include("apps.inventory.urls")),
    path("api/sales/", include("apps.sales.urls")),
]
