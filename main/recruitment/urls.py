from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import StaffApplicationViewSet

router = DefaultRouter()
router.register(r"applications", StaffApplicationViewSet, basename="staffapplication")

urlpatterns = [
    path("", include(router.urls)),
]