from django.urls import path

from .views import NumberingListView

urlpatterns = [
    path("numbering/", NumberingListView.as_view(), name="numbering-list"),
]
