"""En el admin, los campos protegidos no se editan (iteracion-26 #20 · SEC-03).

El estado de una cotización, de un proyecto, de una invitación o de una
suscripción cambia sólo por su acción; el precio de mano de obra de un avance
lo copia su servicio; el folio lo asigna el suyo. Y de quién es un registro —su
cuenta, su proyecto, su persona— se elige al crearlo desde el admin y después
ya no cambia: mover un registro de cuenta lo saca de la empresa que lo hizo.
"""

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.projects.models import Project
from apps.projects.tests.test_projects import make_project
from apps.team.models import Invitation
from apps.team.tests.factories import InvitationFactory

#: (modelo, de solo lectura siempre, se eligen sólo al crear)
PROTECTED_IN_ADMIN = [
    ("accounts.Subscription", {"status"}, {"user"}),
    ("accounts.Organization", set(), {"user"}),
    ("catalog.Tariff", set(), {"owner"}),
    ("clients.Client", set(), {"owner"}),
    ("planner.Plan", set(), {"owner"}),
    ("assets.PlanAsset", set(), {"owner"}),
    ("assets.CatalogModel", set(), {"owner"}),
    ("quotes.Quote", {"status", "folio"}, {"owner"}),
    ("projects.Project", {"status", "folio"}, {"owner", "quote"}),
    ("projects.Progress", {"labor_unit_price"}, {"project", "quote_item"}),
    ("payments.Payment", {"folio"}, {"owner", "project"}),
    ("staff.Worker", set(), {"owner"}),
    ("staff.Assignment", set(), {"project", "quote_item", "worker"}),
    ("staff.WorkerPayment", {"folio"}, {"owner", "worker"}),
    ("team.Invitation", {"status"}, {"account", "email"}),
    ("team.Membership", set(), {"account", "user"}),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("label", "always", "on_create"), PROTECTED_IN_ADMIN)
def test_protected_fields_are_never_edited_in_the_admin(
    rf, admin_user, label, always, on_create
) -> None:
    """SEC-03 - Lo equivalente en apps a la línea base de plataforma (va en #29)."""
    model = apps.get_model(label)
    model_admin = admin.site._registry[model]
    request = rf.get("/admin/")
    request.user = admin_user

    add_form = set(model_admin.get_form(request).base_fields)
    change_form = set(model_admin.get_form(request, obj=model()).base_fields)

    assert not always & add_form, f"{label}: se editan al crear"
    assert on_create <= add_form, f"{label}: control, se eligen al crear"
    assert not (always | on_create) & change_form, f"{label}: se editan después"


@pytest.mark.django_db
class TestTheChangeFormIgnoresThem:
    """SEC-03 - Mandarlos en el formulario de cambio no los cambia."""

    def test_a_finished_status_or_another_owner_is_not_saved(
        self, admin_client
    ) -> None:
        owner = UserFactory()
        project, _muro, _zocalo = make_project(owner)
        other = UserFactory()

        response = admin_client.post(
            reverse("admin:projects_project_change", args=[project.pk]),
            {
                "owner": str(other.pk),
                "quote": str(project.quote_id),
                "status": Project.Status.FINISHED,
            },
        )

        assert response.status_code == 302
        project.refresh_from_db()
        assert project.status == Project.Status.IN_PROGRESS
        assert project.owner_id == owner.id

    def test_an_invitation_is_not_accepted_from_the_admin(self, admin_client) -> None:
        invitation = InvitationFactory(email="mar@despacho.mx")
        other = UserFactory()

        response = admin_client.post(
            reverse("admin:team_invitation_change", args=[invitation.pk]),
            {
                "account": str(other.pk),
                "email": "otra@despacho.mx",
                "status": Invitation.Status.ACCEPTED,
            },
        )

        assert response.status_code == 302
        invitation.refresh_from_db()
        assert invitation.status == Invitation.Status.PENDING
        assert invitation.email == "mar@despacho.mx"
        assert invitation.account_id != other.id
