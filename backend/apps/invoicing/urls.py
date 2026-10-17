from django.urls import path

from .views import (
    ContingencyBlockView, FiscalDocumentDetailView, FiscalDocumentListView, FiscalDocumentRetryView,
    InvoicingStatusView, NumberingListView,
)

urlpatterns = [
    path("status/", InvoicingStatusView.as_view(), name="invoicing-status"),
    path("numbering/", NumberingListView.as_view(), name="numbering-list"),
    path("contingency-blocks/", ContingencyBlockView.as_view(), name="contingency-block"),
    path("documents/", FiscalDocumentListView.as_view(), name="fiscal-document-list"),
    path("documents/<int:pk>/", FiscalDocumentDetailView.as_view(), name="fiscal-document-detail"),
    path("documents/<int:pk>/retry/", FiscalDocumentRetryView.as_view(), name="fiscal-document-retry"),
]
