from rest_framework.routers import DefaultRouter
from .views import GroupViewSet

router = DefaultRouter()
router.register("groups", GroupViewSet, basename="group")

urlpatterns = router.urls