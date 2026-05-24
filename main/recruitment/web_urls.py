from django.urls import path
from .views import application_list_view, application_detail_view

urlpatterns = [
    path("list/", application_list_view, name="application-list"),
    path("list/<int:pk>/", application_detail_view, name="application-detail"),
]