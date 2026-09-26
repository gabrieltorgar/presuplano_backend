"""Projects views: start project, register and correct progress, evidence."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.projects.selectors import (
    evidences_for_owner,
    list_projects_for_owner,
    progresses_for_owner,
)
from apps.projects.serializers import (
    EvidenceSerializer,
    ProgressInputSerializer,
    ProgressSerializer,
    ProgressUpdateSerializer,
    ProjectSerializer,
    StartProjectSerializer,
)
from apps.projects.services import (
    add_evidence,
    delete_evidence,
    delete_progress,
    finalize_project,
    register_progress,
    start_project,
    update_progress,
)


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

    @action(detail=True, methods=["get"])
    def distribution(self, request: Request, pk: str | None = None) -> Response:
        """Cómo está repartida la obra: quién lleva qué y qué falta por repartir."""
        from apps.staff.selectors import project_distribution

        return Response(project_distribution(project=self.get_object()))

    @action(detail=True, methods=["post"])
    def finalize(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        confirm = bool(request.data.get("confirm", False))
        summary = finalize_project(project=project, confirm=confirm)
        return Response(summary)


class ProgressViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve, correct or delete a progress entry; attach its photos."""

    serializer_class = ProgressSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return progresses_for_owner(owner=self.request.user)

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        progress = self.get_object()
        serializer = ProgressUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        progress = update_progress(progress=progress, **serializer.validated_data)
        return Response(ProgressSerializer(progress).data)

    def destroy(self, request: Request, pk: str | None = None) -> Response:
        delete_progress(progress=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

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
            EvidenceSerializer(evidence, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EvidenceViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Quitar una foto de un avance."""

    serializer_class = EvidenceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return evidences_for_owner(owner=self.request.user)

    def perform_destroy(self, instance) -> None:
        delete_evidence(evidence=instance)
