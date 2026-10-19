from django.urls import path

from .admin_views import (
    CategoryDetailView, CategoryListView, PresentationCreateView, PresentationDetailView, PriceHistoryView,
    ProductAdminDetailView, ProductAdminListView, UnitListView,
)
from .views import ProductListView

urlpatterns = [
    path("products/", ProductListView.as_view(), name="product-list"),
    # Administración del catálogo (spec 006)
    path("admin/products/", ProductAdminListView.as_view(), name="product-admin-list"),
    path("admin/products/<int:pk>/", ProductAdminDetailView.as_view(), name="product-admin-detail"),
    path("admin/products/<int:pk>/units/", PresentationCreateView.as_view(), name="presentation-create"),
    path("admin/products/<int:pk>/price-history/", PriceHistoryView.as_view(), name="price-history"),
    path("admin/units/<int:pk>/", PresentationDetailView.as_view(), name="presentation-detail"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("categories/<int:pk>/", CategoryDetailView.as_view(), name="category-detail"),
    path("units/", UnitListView.as_view(), name="unit-list"),
]
