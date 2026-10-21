from django.urls import path

from .quote_api import QuoteConvertView, QuoteDetailView, QuoteDuplicateView, QuoteListView, QuoteVoidView

urlpatterns = [
    path("", QuoteListView.as_view(), name="quote-list"),
    path("<int:pk>/", QuoteDetailView.as_view(), name="quote-detail"),
    path("<int:pk>/void/", QuoteVoidView.as_view(), name="quote-void"),
    path("<int:pk>/duplicate/", QuoteDuplicateView.as_view(), name="quote-duplicate"),
    path("<int:pk>/order/", QuoteConvertView.as_view(), name="quote-order"),
]
