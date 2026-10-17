from django.urls import path

from .views import FiscalDocumentDetailView, FiscalDocumentListView, FiscalDocumentRetryView, NumberingListView

urlpatterns = [
    path("numbering/", NumberingListView.as_view(), name="numbering-list"),
    path("documents/", FiscalDocumentListView.as_view(), name="fiscal-document-list"),
    path("documents/<int:pk>/", FiscalDocumentDetailView.as_view(), name="fiscal-document-detail"),
    path("documents/<int:pk>/retry/", FiscalDocumentRetryView.as_view(), name="fiscal-document-retry"),
]
