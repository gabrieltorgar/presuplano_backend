"""Una ruta de detalle con un registro de otra empresa: 404 y nada cambia.

SEC-02 · MAN-03 (iteracion-26 #22). Cada ruta de ``SCOPED_DETAIL_ROUTES``,
con cada método, pedida por alguien de otra empresa —staff o no: ser staff
no abre otras empresas—. La RLS es la segunda capa; ésta es la primera, el
selector con alcance, y corre también en SQLite.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.test_delete_account import full_account
from apps.assets.models import PlanAsset
from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.payments.models import Payment
from apps.planner.models import Plan
from apps.projects.models import Evidence, Progress, Project
from apps.quotes.models import Quote
from apps.staff.models import Assignment, Worker, WorkerPayment
from apps.team.models import Invitation, Membership
from apps.team.tests.factories import InvitationFactory, MembershipFactory
from tests.security.scope_registry import SCOPED_DETAIL_ROUTES

#: El registro que pide cada ruta (el tramo antes de ``{pk}``) y su empresa.
RECORDS = {
    "tariffs": (Tariff, "owner"),
    "clients": (Client, "owner"),
    "quotes": (Quote, "owner"),
    "projects": (Project, "owner"),
    "progresses": (Progress, "project__owner"),
    "evidences": (Evidence, "progress__project__owner"),
    "payments": (Payment, "owner"),
    "plans": (Plan, "owner"),
    "workers": (Worker, "owner"),
    "assignments": (Assignment, "project__owner"),
    "worker-payments": (WorkerPayment, "owner"),
    "plan-assets": (PlanAsset, "owner"),
    "members": (Membership, "account"),
    "invitations": (Invitation, "account"),
}

#: Un cuerpo válido donde la vista valida antes de buscar el registro: así el
#: 404 sale de la búsqueda y no de un 400 que la tapa.
BODIES = {("patch", "/api/collaborators/members/{pk}/"): {"is_active": False}}


def _record_of(route: str, company):
    parts = route.strip("/").split("/")
    model, company_field = RECORDS[parts[parts.index("{pk}") - 1]]
    return model, model.objects.filter(**{company_field: company}).first()


@pytest.fixture
def other_company(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    # Aquí no se prueba la contraseña: un hash rápido para 82 casos.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    company = UserFactory()
    full_account(company)
    MembershipFactory(account=company)
    InvitationFactory(account=company)
    return company


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "route"), SCOPED_DETAIL_ROUTES)
@pytest.mark.parametrize("staff", [False, True], ids=["user", "staff"])
def test_another_companys_record_is_not_found_and_stays(
    method, route, staff, other_company, mocker
):
    """SEC-02 · MAN-03"""
    sent = mocker.patch("common.mail.send_email", return_value=True)
    model, record = _record_of(route, other_company)
    assert record is not None, f"falta un {model.__name__} en la otra empresa"
    before = model.objects.filter(pk=record.pk).values().get()
    intruder = APIClient()
    intruder.force_authenticate(user=UserFactory(is_staff=staff))

    response = getattr(intruder, method)(
        route.format(pk=record.pk), BODIES.get((method, route), {}), format="json"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert model.objects.filter(pk=record.pk).values().get() == before
    assert not sent.called
