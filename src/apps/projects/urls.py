"""Projects URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.projects.views import ProgressViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("progresses", ProgressViewSet, basename="progress")

urlpatterns = router.urls
