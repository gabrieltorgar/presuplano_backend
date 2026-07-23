"""Projects views: start project, register progress, attach evidence."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.projects.selectors import list_projects_for_owner, progresses_for_owner
from apps.projects.serializers import (
    EvidenceSerializer,
    ProgressInputSerializer,
    ProgressSerializer,
    ProjectSerializer,
    StartProjectSerializer,
)
from apps.projects.services import add_evidence, register_progress, start_project


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve projects; start a project; register progress."""

    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return list_projects_for_owner(owner=self.request.user)

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = StartProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = start_project(
            owner=request.user, quote=serializer.validated_data["quote"]
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def progress(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        serializer = ProgressInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = register_progress(project=project, **serializer.validated_data)
        return Response(ProgressSerializer(entry).data, status=status.HTTP_201_CREATED)


class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve a progress entry; attach photographic evidence."""

    serializer_class = ProgressSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return progresses_for_owner(owner=self.request.user)

    @action(detail=True, methods=["post"])
    def evidence(self, request: Request, pk: str | None = None) -> Response:
        progress = self.get_object()
        image = request.FILES.get("image")
        if image is None:
            return Response(
                {"image": ["La imagen es obligatoria."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        evidence = add_evidence(progress=progress, image=image)
        return Response(
            EvidenceSerializer(evidence).data, status=status.HTTP_201_CREATED
        )
