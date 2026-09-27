"""US-126 — eliminar la cuenta borra todo, archivos incluidos. No anonimiza.

Una cuenta que se va no deja nada: ni filas en la base, ni el logotipo, las
fotografías, las texturas o el mobiliario en el bucket —tampoco los archivos
que ya ninguna fila recordaba—. Lo de otras cuentas no se toca.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from rest_framework import status

from apps.accounts.models import Organization, OtpCode, Subscription, User
from apps.accounts.services import get_my_organization, issue_otp
from apps.assets.models import CatalogModel, PlanAsset
from apps.assets.services import store_asset, store_models
from apps.catalog.models import Tariff
from apps.clients.models import Client
from apps.legal.models import LegalAcceptance
from apps.legal.tests.consent import accepted
from apps.payments.models import Payment
from apps.payments.services import register_payment
from apps.planner.models import Plan
from apps.projects.models import Evidence, Progress, Project
from apps.projects.services import add_evidence, register_progress
from apps.projects.tests.test_projects import make_project, png_file
from apps.quotes.models import Quote, QuoteItem
from apps.staff.models import Assignment, Worker, WorkerPayment, WorkerService
from apps.staff.services import assign_service, pay_worker
from apps.staff.tests.factories import WorkerFactory

DELETE = "/api/auth/me/delete/"


def full_account(user) -> dict[str, str]:
    """Una cuenta con algo de todo, y los archivos que dejó en el bucket."""
    Subscription.objects.get_or_create(user=user)
    organization = get_my_organization(user=user)
    organization.logo.save("logo.png", png_file("logo.png"))

    project, muro, _zocalo = make_project(user)
    worker = WorkerFactory(owner=user, name="Juan Pérez")
    WorkerService.objects.create(worker=worker, tariff=muro.tariff, unit_price="90")
    assign_service(
        project=project, quote_item=muro, worker=worker, quantity=Decimal("4")
    )
    progress = register_progress(
        project=project,
        quote_item=muro,
        quantity=Decimal("2"),
        date=date(2026, 1, 10),
        worker=worker,
    )
    evidence = add_evidence(progress=progress, image=png_file("obra.png"))
    register_payment(
        owner=user, project=project, amount=Decimal("500"), date=date(2026, 1, 11)
    )
    pay_worker(
        owner=user,
        worker=worker,
        amount=Decimal("100"),
        date=date(2026, 1, 12),
        project=project,
    )

    Plan.objects.create(owner=user, name="Casa", document={"version": 3})
    asset, _ = store_asset(
        owner=user,
        kind="texture",
        path="texturas/madera.png",
        file=png_file("madera.png"),
    )
    store_models(owner=user, fiches=[{"id": "silla", "name": "Silla"}])
    LegalAcceptance.objects.create(user=user, document="terms", version="2026-09-26")
    issue_otp(user=user, purpose=OtpCode.Purpose.SIGNUP)
    return {
        "logo": organization.logo.name,
        "evidence": evidence.image.name,
        "asset": asset.file.name,
        "org_prefix": f"{organization.pk}/",
        "evidence_prefix": f"evidence/{user.pk}/",
    }


def owned_rows(user_id) -> dict[str, int]:
    """Cuántas filas le quedan a esa cuenta en cada tabla."""
    return {
        "user": User.objects.filter(pk=user_id).count(),
        "organization": Organization.objects.filter(user_id=user_id).count(),
        "subscription": Subscription.objects.filter(user_id=user_id).count(),
        "otp": OtpCode.objects.filter(user_id=user_id).count(),
        "legal": LegalAcceptance.objects.filter(user_id=user_id).count(),
        "tariffs": Tariff.objects.filter(owner_id=user_id).count(),
        "clients": Client.objects.filter(owner_id=user_id).count(),
        "quotes": Quote.objects.filter(owner_id=user_id).count(),
        "quote_items": QuoteItem.objects.filter(quote__owner_id=user_id).count(),
        "projects": Project.objects.filter(owner_id=user_id).count(),
        "progress": Progress.objects.filter(project__owner_id=user_id).count(),
        "evidence": Evidence.objects.filter(
            progress__project__owner_id=user_id
        ).count(),
        "payments": Payment.objects.filter(owner_id=user_id).count(),
        "workers": Worker.objects.filter(owner_id=user_id).count(),
        "worker_services": WorkerService.objects.filter(
            worker__owner_id=user_id
        ).count(),
        "assignments": Assignment.objects.filter(project__owner_id=user_id).count(),
        "worker_payments": WorkerPayment.objects.filter(owner_id=user_id).count(),
        "plans": Plan.objects.filter(owner_id=user_id).count(),
        "plan_assets": PlanAsset.objects.filter(owner_id=user_id).count(),
        "catalog_models": CatalogModel.objects.filter(owner_id=user_id).count(),
    }


@pytest.fixture
def media(settings, tmp_path) -> Path:
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


@pytest.mark.django_db
class TestEliminarLaCuenta:
    """US-126: eliminar la cuenta, confirmándolo con la contraseña."""

    def test_everything_goes_rows_and_files(
        self, authenticated_client, user, media, django_capture_on_commit_callbacks
    ) -> None:
        """Flujo principal - Se borra todo, archivos incluidos."""
        files = full_account(user)
        # Un logotipo reemplazado y una foto a medio subir: ninguna fila los nombra.
        huerfano_logo = media / files["org_prefix"] / "logo" / "logo-viejo.png"
        huerfano_foto = media / files["evidence_prefix"] / "subida-cortada.jpg"
        for huerfano in (huerfano_logo, huerfano_foto):
            huerfano.parent.mkdir(parents=True, exist_ok=True)
            huerfano.write_bytes(b"x")
        user_id = user.pk
        antes = owned_rows(user_id)
        assert [tabla for tabla, filas in antes.items() if not filas] == []

        with django_capture_on_commit_callbacks(execute=True):
            response = authenticated_client.post(DELETE, {"password": "testpass123"})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert owned_rows(user_id) == dict.fromkeys(antes, 0)
        for name in (files["logo"], files["evidence"], files["asset"]):
            assert not (media / name).exists(), name
        assert not huerfano_logo.exists()
        assert not huerfano_foto.exists()

    def test_other_accounts_are_untouched(
        self,
        authenticated_client,
        user,
        user_factory,
        media,
        django_capture_on_commit_callbacks,
    ) -> None:
        """Caso de borde - Lo de otra cuenta se queda, con sus archivos."""
        otra = user_factory()
        files_otra = full_account(otra)
        full_account(user)
        antes = owned_rows(otra.pk)

        with django_capture_on_commit_callbacks(execute=True):
            authenticated_client.post(DELETE, {"password": "testpass123"})

        assert owned_rows(otra.pk) == antes
        for key in ("logo", "evidence", "asset"):
            assert (media / files_otra[key]).exists(), key

    def test_a_wrong_password_deletes_nothing(
        self, authenticated_client, user, media
    ) -> None:
        """Caso alternativo - Sin la contraseña correcta no se borra nada."""
        files = full_account(user)
        antes = owned_rows(user.pk)

        response = authenticated_client.post(DELETE, {"password": "otra-cosa"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "La contraseña no es correcta" in str(response.data)
        assert owned_rows(user.pk) == antes
        assert (media / files["logo"]).exists()

    def test_the_session_dies_with_the_account(self, api_client, user_factory) -> None:
        """Caso de borde - La sesión de una cuenta borrada ya no abre nada."""
        user_factory(email="ana@estudio.mx", password="testpass123")
        login = api_client.post(
            "/api/auth/login/", {"email": "ana@estudio.mx", "password": "testpass123"}
        )
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        assert api_client.post(DELETE, {"password": "testpass123"}).status_code == 204
        assert (
            api_client.get("/api/auth/me/").status_code == status.HTTP_401_UNAUTHORIZED
        )

    def test_the_email_can_be_used_again(
        self, authenticated_client, api_client, user
    ) -> None:
        """Caso de borde - Borrada, no queda rastro que impida volver a registrarse."""
        email = user.email
        authenticated_client.post(DELETE, {"password": "testpass123"})

        response = api_client.post(
            "/api/auth/register/",
            {"email": email, "password": "secret123", **accepted()},
        )

        assert response.status_code == status.HTTP_201_CREATED

    def test_an_account_without_files_is_deleted_too(
        self, authenticated_client, user, media, django_capture_on_commit_callbacks
    ) -> None:
        """Caso de borde - Una cuenta recién creada, sin nada en el bucket."""
        with django_capture_on_commit_callbacks(execute=True):
            response = authenticated_client.post(DELETE, {"password": "testpass123"})

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not User.objects.filter(pk=user.pk).exists()

    def test_it_needs_a_session_and_the_password(
        self, api_client, authenticated_client
    ) -> None:
        """Caso de borde - Sin sesión o sin contraseña no hay borrado."""
        assert api_client.post(DELETE, {"password": "x"}).status_code == 401
        response = authenticated_client.post(DELETE, {})
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Escribe tu contraseña para confirmar" in str(response.data)


def test_a_file_that_is_already_gone_does_not_stop_the_rest() -> None:
    """Caso de borde - Un archivo que ya no está no frena el borrado de los demás."""
    from apps.accounts.deletion import _remove

    class Storage:
        def __init__(self):
            self.deleted = []

        def delete(self, name):
            if name == "roto":
                raise OSError("no está")
            self.deleted.append(name)

    storage = Storage()
    _remove([(storage, "roto"), (storage, "bien"), (storage, "bien")])

    assert storage.deleted == ["bien"]
