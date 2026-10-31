"""Projects views: start project, register and correct progress, evidence."""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.projects.filters import ProgressFilter, ProjectFilter
from apps.projects.selectors import (
    evidences_for_owner,
    list_projects_for_owner,
    progresses_for_owner,
    project_rows_for_owner,
)
from apps.projects.serializers import (
    EvidenceSerializer,
    ProgressInputSerializer,
    ProgressSerializer,
    ProgressUpdateSerializer,
    ProjectListSerializer,
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
from apps.team.tenancy import account_of
from common.permissions import IsVerifiedUser


class ProjectViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve projects; start a project; register progress.

    The list (US-67, iteracion-17) brings rows without progress entries or
    photos: ``?status=a,b`` and ``?id=a,b``; searches by client; orders by
    progress, quoted value or client, least progress first by default. Each
    project is asked for on its own, with everything its screen shows.
    """

    serializer_class = ProjectSerializer
    permission_classes = [IsVerifiedUser]
    filterset_class = ProjectFilter
    search_fields = ("quote__client__name",)
    ordering_fields = (
        "progress_percentage",
        "quoted_value",
        "client_name",
        "created_at",
    )
    ordering_text_fields = ("client_name",)
    ordering = ("progress_percentage", "-created_at", "id")

    def get_queryset(self):
        owner = account_of(self.request)
        if self.action == "list":
            return project_rows_for_owner(owner=owner)
        return list_projects_for_owner(owner=owner)

    def get_serializer_class(self):
        return ProjectListSerializer if self.action == "list" else ProjectSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = StartProjectSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        project = start_project(
            owner=account_of(request), quote=serializer.validated_data["quote"]
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def progress(self, request: Request, pk: str | None = None) -> Response:
        project = self.get_object()
        serializer = ProgressInputSerializer(
            data=request.data, context={"request": request}
        )
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
    permission_classes = [IsVerifiedUser]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    # La lista (iteracion-17): por páginas, por proyecto, partida o persona, y en
    # el orden en que se trabajó.
    filterset_class = ProgressFilter
    search_fields = ("quote_item__name", "worker__name")
    ordering_fields = ("date", "quantity", "created_at")
    ordering = ("date", "created_at", "id")

    def get_queryset(self):
        return progresses_for_owner(owner=account_of(self.request))

    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        progress = self.get_object()
        serializer = ProgressUpdateSerializer(
            data=request.data, partial=True, context={"request": request}
        )
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
    permission_classes = [IsVerifiedUser]

    def get_queryset(self):
        return evidences_for_owner(owner=account_of(self.request))

    def perform_destroy(self, instance) -> None:
        delete_evidence(evidence=instance)
