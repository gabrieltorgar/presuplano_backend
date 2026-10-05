"""Projects URLs (router)."""

from rest_framework.routers import DefaultRouter

from apps.projects.views import EvidenceViewSet, ProgressViewSet, ProjectViewSet

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")
router.register("progresses", ProgressViewSet, basename="progress")
router.register("evidences", EvidenceViewSet, basename="evidence")

urlpatterns = router.urls
