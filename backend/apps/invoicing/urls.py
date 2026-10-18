from django.urls import path

from .views import (
    ContingencyBlockView, FiscalDocumentDetailView, FiscalDocumentListView, FiscalDocumentRetryView,
    BusinessView, FiscalDocumentSendView, InvoicingStatusView, NumberingListView, TicketView,
)

urlpatterns = [
    path("status/", InvoicingStatusView.as_view(), name="invoicing-status"),
    path("numbering/", NumberingListView.as_view(), name="numbering-list"),
    path("contingency-blocks/", ContingencyBlockView.as_view(), name="contingency-block"),
    path("documents/", FiscalDocumentListView.as_view(), name="fiscal-document-list"),
    path("documents/<int:pk>/", FiscalDocumentDetailView.as_view(), name="fiscal-document-detail"),
    path("documents/<int:pk>/retry/", FiscalDocumentRetryView.as_view(), name="fiscal-document-retry"),
    path("documents/<int:pk>/send/", FiscalDocumentSendView.as_view(), name="fiscal-document-send"),
    path("business/", BusinessView.as_view(), name="business"),
    path("ticket/<int:sale_id>/", TicketView.as_view(), name="ticket"),
]
