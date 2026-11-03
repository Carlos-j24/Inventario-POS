from django.urls import path

from .api import CategoryDetailView, CategoryListView, ExpenseDetailView, ExpenseListView, ExpenseVoidView

urlpatterns = [
    path("", ExpenseListView.as_view(), name="expense-list"),
    path("categories/", CategoryListView.as_view(), name="expense-category-list"),
    path("categories/<int:pk>/", CategoryDetailView.as_view(), name="expense-category-detail"),
    path("<int:pk>/", ExpenseDetailView.as_view(), name="expense-detail"),
    path("<int:pk>/void/", ExpenseVoidView.as_view(), name="expense-void"),
]
