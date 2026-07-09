from rest_framework.routers import DefaultRouter
from .views import ExpenseViewSet, SettlementViewSet

router = DefaultRouter()
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("settlements", SettlementViewSet, basename="settlement")

urlpatterns = router.urls