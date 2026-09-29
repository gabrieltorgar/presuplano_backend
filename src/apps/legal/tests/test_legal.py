"""US-121 a US-123 — los documentos legales, su aceptación y su actualización.

Los términos y la política de privacidad viven en el repositorio con una
versión. Una cuenta nueva los acepta al registrarse; una que ya existía, o que
aceptó una versión anterior, los vuelve a ver hasta aceptarlos.
"""

import pytest
from rest_framework import status

from apps.accounts.models import User
from apps.legal import documents
from apps.legal.documents import LegalDocument, parse
from apps.legal.models import LegalAcceptance
from apps.legal.tests.consent import accepted

LEGAL = "/api/legal/"
ACCEPT = "/api/legal/accept/"
REGISTER = "/api/auth/register/"
ME = "/api/auth/me/"


@pytest.fixture
def new_version(monkeypatch):
    """Publica una versión nueva de los términos, sin tocar el archivo."""
    original = documents.load

    def bump(kind: str) -> LegalDocument:
        doc = original(kind)
        if kind != "terms":
            return doc
        return LegalDocument(
            kind=doc.kind, title=doc.title, version="2099-01-01", body=doc.body
        )

    monkeypatch.setattr(documents, "load", bump)
    return "2099-01-01"


@pytest.mark.django_db
class TestLosDocumentos:
    """US-121: los términos y la política se leen sin cuenta."""

    def test_both_documents_are_listed_with_their_version(self, api_client) -> None:
        """Flujo principal - Qué documentos hay y qué versión rige."""
        response = api_client.get(LEGAL)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["terms"]["title"] == "Términos y condiciones"
        assert response.data["privacy"]["title"] == "Política de privacidad"
        assert response.data["terms"]["version"]
        assert response.data["privacy"]["version"]

    @pytest.mark.parametrize(
        ("kind", "must_say"),
        [
            ("terms", "no representan un acuerdo ni un contrato"),
            ("privacy", "No hay finalidades secundarias"),
        ],
    )
    def test_each_document_brings_its_text(self, api_client, kind, must_say) -> None:
        """Flujo principal - El texto completo, en Markdown."""
        response = api_client.get(f"{LEGAL}{kind}/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["kind"] == kind
        assert must_say in response.data["body"]
        # La cabecera no se cuela en el cuerpo.
        assert not response.data["body"].startswith("---")

    def test_the_texts_say_what_deleting_the_account_does(self, api_client) -> None:
        """Flujo principal - Los dos avisan que borrar la cuenta borra, no anonimiza."""
        terms = api_client.get(f"{LEGAL}terms/").data["body"]
        privacy = api_client.get(f"{LEGAL}privacy/").data["body"]

        assert "No se anonimiza nada: se borra" in terms
        assert "No se anonimiza: se borra." in privacy

    def test_the_texts_carry_the_new_name(self, api_client) -> None:
        """US-127 - Los dos hablan de CUOTREKA y dicen cómo se llamaba."""
        for kind in ("terms", "privacy"):
            body = api_client.get(f"{LEGAL}{kind}/").data["body"]

            assert "CUOTREKA antes se llamaba presuplano." in body
            # Fuera de esa nota, el nombre de antes sólo sobrevive en el dominio.
            resto = body.replace("CUOTREKA antes se llamaba presuplano.", "")
            assert "presuplano" not in resto.replace("presuplano.vercel.app", "")

    def test_an_unknown_document_is_not_found(self, api_client) -> None:
        """Caso de borde - Sólo hay dos documentos."""
        assert (
            api_client.get(f"{LEGAL}cookies/").status_code == status.HTTP_404_NOT_FOUND
        )

    def test_a_document_without_its_header_is_refused(self) -> None:
        """Caso de borde - Un archivo sin versión no puede publicarse."""
        with pytest.raises(ValueError, match="cabecera"):
            parse("# Sin cabecera\n")
        with pytest.raises(ValueError, match="no se cierra"):
            parse("---\ntitle: x\n")
        meta, body = parse("---\ntitle: T\nversion: 1\n---\n\nHola\n")
        assert meta == {"title": "T", "version": "1"}
        assert body == "Hola\n"


@pytest.mark.django_db
class TestAceptarAlRegistrarse:
    """US-122: crear la cuenta exige aceptar las versiones vigentes."""

    def test_registering_records_what_was_accepted_and_from_where(
        self, api_client
    ) -> None:
        """Flujo principal - La constancia lleva versión, IP y navegador."""
        response = api_client.post(
            REGISTER,
            {"email": "ana@estudio.mx", "password": "secret123", **accepted()},
            HTTP_USER_AGENT="Navegador de prueba",
            HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1",
        )

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(email="ana@estudio.mx")
        constancias = {a.document: a for a in user.legal_acceptances.all()}
        assert set(constancias) == {"terms", "privacy"}
        assert constancias["terms"].version == accepted()["terms_version"]
        assert constancias["terms"].ip_address == "203.0.113.7"
        assert constancias["privacy"].user_agent == "Navegador de prueba"

    def test_without_accepting_there_is_no_account(self, api_client) -> None:
        """Caso alternativo - Sin aceptar no se crea la cuenta."""
        response = api_client.post(
            REGISTER, {"email": "ana@estudio.mx", "password": "secret123"}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Acepta los términos y condiciones" in str(
            response.data["terms_version"]
        )
        assert "Acepta la política de privacidad" in str(
            response.data["privacy_version"]
        )
        assert not User.objects.exists()

    def test_an_outdated_version_is_refused(self, api_client) -> None:
        """Caso de borde - Si cambiaron mientras se llenaba el formulario."""
        response = api_client.post(
            REGISTER,
            {
                "email": "ana@estudio.mx",
                "password": "secret123",
                "terms_version": "2000-01-01",
                "privacy_version": accepted()["privacy_version"],
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "cambiaron" in str(response.data["terms_version"])
        assert not User.objects.exists()


@pytest.mark.django_db
class TestCuentasQueFaltanPorAceptar:
    """US-123: las cuentas que no han aceptado lo vigente lo aceptan al entrar."""

    def test_an_existing_account_is_asked_to_accept(self, authenticated_client) -> None:
        """Flujo principal - Una cuenta de antes de los documentos."""
        legal = authenticated_client.get(ME).data["legal"]

        assert legal["pending"] is True
        assert legal["terms"]["accepted_version"] is None
        assert legal["terms"]["version"] == accepted()["terms_version"]

    def test_accepting_clears_the_request(self, authenticated_client, user) -> None:
        """Flujo principal - Aceptar deja la cuenta al corriente."""
        response = authenticated_client.post(ACCEPT, accepted(), format="json")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["pending"] is False
        assert authenticated_client.get(ME).data["legal"]["pending"] is False
        assert user.legal_acceptances.count() == 2

    def test_accepting_twice_keeps_a_single_record(
        self, authenticated_client, user
    ) -> None:
        """Caso de borde - Aceptar la misma versión no duplica la constancia."""
        authenticated_client.post(ACCEPT, accepted(), format="json")
        authenticated_client.post(ACCEPT, accepted(), format="json")

        assert user.legal_acceptances.count() == 2

    def test_a_new_version_is_asked_again(
        self, authenticated_client, user, new_version
    ) -> None:
        """Flujo principal - Al actualizarse, se vuelve a pedir a todos."""
        LegalAcceptance.objects.create(
            user=user, document="terms", version="2000-01-01"
        )
        LegalAcceptance.objects.create(
            user=user, document="privacy", version=accepted()["privacy_version"]
        )

        legal = authenticated_client.get(ME).data["legal"]

        assert legal["pending"] is True
        assert legal["terms"] == {
            "version": new_version,
            "accepted_version": "2000-01-01",
        }
        assert legal["privacy"]["accepted_version"] == legal["privacy"]["version"]

        response = authenticated_client.post(
            ACCEPT,
            {
                "terms_version": new_version,
                "privacy_version": accepted()["privacy_version"],
            },
            format="json",
        )
        assert response.data["pending"] is False

    def test_accepting_an_old_version_is_refused(self, authenticated_client) -> None:
        """Caso de borde - Una pantalla vieja no puede aceptar otro texto."""
        response = authenticated_client.post(
            ACCEPT,
            {"terms_version": "2000-01-01", "privacy_version": "2000-01-01"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert set(response.data) == {"terms_version", "privacy_version"}

    def test_accepting_needs_a_session(self, api_client) -> None:
        """Caso de borde - Sin cuenta no hay qué aceptar."""
        response = api_client.post(ACCEPT, accepted(), format="json")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
