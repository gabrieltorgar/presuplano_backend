"""Acceso cruzado entre cuentas (bug iteracion-12 #2, US-18 · US-06 · US-96 · US-31).

Cada cuenta ve, cambia y borra sólo lo suyo. Un registro de otra cuenta no
existe para quien lo pide: el detalle, la edición y el borrado responden 404, y
una referencia ajena en una escritura se rechaza con el mismo mensaje que una
que no existe, para que la respuesta no delate qué hay en otras cuentas.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.services import get_my_organization
from apps.accounts.tests.factories import UserFactory
from apps.catalog.tests.factories import TariffFactory
from apps.clients.tests.factories import ClientFactory
from apps.payments.models import Payment
from apps.payments.services import register_payment
from apps.planner.models import Plan
from apps.projects.services import register_progress, start_project
from apps.quotes.services import create_quote
from apps.staff.models import Worker
from apps.staff.services import pay_worker
from apps.staff.tests.factories import WorkerFactory

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def cuenta_completa(owner):
    """Una cuenta con un registro de cada recurso que se puede pedir."""
    cliente = ClientFactory(owner=owner, name="Constructora Reyes")
    muro = TariffFactory(owner=owner, name="Muro", unit_price="350")
    plano = Plan.objects.create(owner=owner, name="Casa", document={})
    cotizacion = create_quote(
        owner=owner,
        client=cliente,
        items_data=[{"tariff": muro, "quantity": Decimal("10")}],
    )
    proyecto = start_project(owner=owner, quote=cotizacion)
    partida = cotizacion.items.get()
    register_progress(
        project=proyecto, quote_item=partida, quantity=Decimal("4"), date=date.today()
    )
    trabajador = WorkerFactory(owner=owner, name="Luis")
    pago = register_payment(
        owner=owner, project=proyecto, amount=Decimal("500"), date=date.today()
    )
    pay_worker(owner=owner, worker=trabajador, amount=Decimal("100"), date=date.today())
    return {
        "client": cliente,
        "tariff": muro,
        "plan": plano,
        "quote": cotizacion,
        "project": proyecto,
        "quote_item": partida,
        "worker": trabajador,
        "payment": pago,
    }


@pytest.fixture
def mia(user):
    return cuenta_completa(user)


@pytest.fixture
def otra(db):
    return cuenta_completa(UserFactory())


def no_existe(ref) -> str:
    """Un id con la forma de los de verdad que no es de nadie."""
    return str(uuid.uuid4()) if ref is None else str(ref.id)


@pytest.mark.django_db
class TestLoAjenoNoExiste:
    """Detalle, edición y borrado de un registro de otra cuenta: 404."""

    @pytest.mark.parametrize(
        ("url", "clave"),
        [
            ("/api/tariffs/{}/", "tariff"),
            ("/api/clients/{}/", "client"),
            ("/api/quotes/{}/", "quote"),
            ("/api/projects/{}/", "project"),
            ("/api/workers/{}/", "worker"),
            ("/api/payments/{}/", "payment"),
            ("/api/plans/{}/", "plan"),
        ],
    )
    def test_detail_of_another_account_is_not_found(
        self, authenticated_client, otra, url, clave
    ) -> None:
        response = authenticated_client.get(url.format(otra[clave].id))

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize(
        ("url", "clave", "cambio"),
        [
            ("/api/tariffs/{}/", "tariff", {"name": "Mía"}),
            ("/api/clients/{}/", "client", {"name": "Mía"}),
            ("/api/workers/{}/", "worker", {"name": "Mía"}),
        ],
    )
    def test_another_accounts_record_can_be_neither_edited_nor_deleted(
        self, authenticated_client, otra, url, clave, cambio
    ) -> None:
        registro = otra[clave]

        editar = authenticated_client.patch(url.format(registro.id), cambio)
        borrar = authenticated_client.delete(url.format(registro.id))

        assert editar.status_code == status.HTTP_404_NOT_FOUND
        assert borrar.status_code == status.HTTP_404_NOT_FOUND
        registro.refresh_from_db()
        assert registro.name != "Mía"

    def test_another_accounts_imported_file_is_not_found(
        self, authenticated_client, db
    ) -> None:
        ajena = APIClient()
        ajena.force_authenticate(UserFactory())
        subido = ajena.post(
            "/api/plan-assets/",
            {
                "path": "sh3t/azulejo.png",
                "kind": "texture",
                "file": SimpleUploadedFile("azulejo.png", PNG, "image/png"),
            },
            format="multipart",
        )

        response = authenticated_client.get(f"/api/plan-assets/{subido.data['id']}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert authenticated_client.get("/api/plan-assets/").data["results"] == []


@pytest.mark.django_db
class TestPagosDeOtraCuenta:
    """US-18: los pagos, su resumen y su comprobante son de su cuenta."""

    def test_summary_and_voucher_of_another_project_are_not_found(
        self, authenticated_client, otra
    ) -> None:
        proyecto = {"project": str(otra["project"].id)}

        resumen = authenticated_client.get("/api/payments/summary/", proyecto)
        comprobante = authenticated_client.get("/api/payments/voucher/", proyecto)

        assert resumen.status_code == status.HTTP_404_NOT_FOUND
        assert comprobante.status_code == status.HTTP_404_NOT_FOUND

    def test_listing_another_projects_payments_shows_nothing(
        self, authenticated_client, otra
    ) -> None:
        response = authenticated_client.get(
            "/api/payments/", {"project": str(otra["project"].id)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []

    def test_a_payment_cannot_be_registered_on_another_project(
        self, authenticated_client, otra
    ) -> None:
        antes = Payment.objects.count()

        response = authenticated_client.post(
            "/api/payments/",
            {"project": str(otra["project"].id), "amount": "100", "date": "2026-01-15"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Payment.objects.count() == antes

    def test_a_worker_summary_of_another_account_is_not_found(
        self, authenticated_client, otra
    ) -> None:
        response = authenticated_client.get(
            "/api/worker-payments/summary/", {"worker": str(otra["worker"].id)}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestReferenciasAcotadasALaCuenta:
    """Una referencia ajena se rechaza igual que una que no existe.

    Antes, el registro ajeno pasaba la validación de entrada y lo rechazaba el
    servicio con su propio mensaje; uno inexistente, el campo con otro. La
    diferencia bastaba para saber qué ids existen en otras cuentas.
    """

    def _escrituras(self, mia, ref):
        """Cada escritura que recibe un id, con el id en `ref` y lo demás mío."""
        partida = {"tariff": str(mia["tariff"].id), "quantity": "2"}
        return {
            "client": (
                "/api/quotes/",
                {"client": no_existe(ref("client")), "items": [partida]},
                "client",
            ),
            "tariff": (
                "/api/quotes/",
                {
                    "client": str(mia["client"].id),
                    "items": [{"tariff": no_existe(ref("tariff")), "quantity": "2"}],
                },
                "items",
            ),
            "plan": (
                "/api/quotes/",
                {
                    "client": str(mia["client"].id),
                    "items": [partida],
                    "plan": no_existe(ref("plan")),
                },
                "plan",
            ),
            "quote": ("/api/projects/", {"quote": no_existe(ref("quote"))}, "quote"),
            "quote_item": (
                f"/api/projects/{mia['project'].id}/progress/",
                {
                    "quote_item": no_existe(ref("quote_item")),
                    "quantity": "1",
                    "date": "2026-01-15",
                },
                "quote_item",
            ),
            "worker": (
                "/api/worker-payments/",
                {
                    "worker": no_existe(ref("worker")),
                    "amount": "100",
                    "date": "2026-01-15",
                },
                "worker",
            ),
            "project": (
                "/api/payments/",
                {
                    "project": no_existe(ref("project")),
                    "amount": "100",
                    "date": "2026-01-15",
                },
                "project",
            ),
        }

    @pytest.mark.parametrize(
        "clave",
        ["client", "tariff", "plan", "quote", "quote_item", "worker", "project"],
    )
    def test_a_foreign_reference_reads_like_a_missing_one(
        self, authenticated_client, mia, otra, clave
    ) -> None:
        url, ajeno, campo = self._escrituras(mia, lambda k: otra[k])[clave]
        _, inexistente, _ = self._escrituras(mia, lambda k: None)[clave]

        con_ajeno = authenticated_client.post(url, ajeno, format="json")
        con_inexistente = authenticated_client.post(url, inexistente, format="json")

        assert con_ajeno.status_code == status.HTTP_400_BAD_REQUEST
        assert campo in con_ajeno.data
        # Mismo mensaje: la respuesta no dice si el id existe en otra cuenta.
        assert con_ajeno.data == con_inexistente.data

    def test_a_worker_service_from_another_catalogue_is_refused(
        self, authenticated_client, otra
    ) -> None:
        response = authenticated_client.post(
            "/api/workers/",
            {
                "name": "Pedro",
                "kind": Worker.Kind.PERSON,
                "services": [
                    {"tariff": str(otra["tariff"].id), "unit_price": "50"}
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Worker.objects.filter(name="Pedro").exists()

    def test_handing_out_a_foreign_project_is_refused(
        self, authenticated_client, mia, otra
    ) -> None:
        response = authenticated_client.post(
            "/api/assignments/",
            {
                "project": str(otra["project"].id),
                "quote_item": str(otra["quote_item"].id),
                "worker": str(mia["worker"].id),
                "quantity": "1",
            },
            format="json",
        )

        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
        )
        assert not otra["project"].assignments.exists()


@pytest.mark.django_db
class TestDocumentosConSuPropiaMarca:
    """US-31: un documento sale con el membrete de quien lo manda, nunca otro."""

    def test_the_letterhead_is_the_senders(
        self, authenticated_client, user, settings, mocker
    ) -> None:
        settings.RESEND_API_KEY = "re_test"
        correo = mocker.patch("common.mail.send_email", return_value=True)
        mia = get_my_organization(user=user)
        mia.name = "Estudio Propio"
        mia.save()
        ajena = get_my_organization(user=UserFactory())
        ajena.name = "Estudio Ajeno"
        ajena.save()

        authenticated_client.post(
            "/api/documents/send/",
            {
                "kind": "quote",
                "to": "cliente@correo.mx",
                "file": SimpleUploadedFile("c.pdf", b"%PDF-1.4 x", "application/pdf"),
            },
            format="multipart",
        )

        html = correo.call_args.kwargs["html"]
        assert "Estudio Propio" in html
        assert "Estudio Ajeno" not in html

