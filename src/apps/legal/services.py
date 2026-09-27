"""Legal business logic: qué versión está vigente y quién la aceptó."""

import logging

from rest_framework.exceptions import ValidationError

from apps.legal import documents
from apps.legal.models import LegalAcceptance, LegalDocumentKind

logger = logging.getLogger("apps")

#: Lo que cabe del navegador en la constancia; el resto no identifica más.
USER_AGENT_MAX = 300


def check_versions(*, terms_version: str, privacy_version: str) -> None:
    """Que lo aceptado sea lo vigente.

    Quien tenía la pantalla abierta mientras se publicaba una versión nueva
    aceptaría un texto que ya no es el que rige; mejor pedírselo otra vez.

    Raises:
        ValidationError: alguna de las dos no es la vigente.
    """
    current = documents.current_versions()
    errors = {}
    if terms_version != current[LegalDocumentKind.TERMS]:
        errors["terms_version"] = (
            "Los términos y condiciones cambiaron; vuelve a leerlos y acéptalos."
        )
    if privacy_version != current[LegalDocumentKind.PRIVACY]:
        errors["privacy_version"] = (
            "La política de privacidad cambió; vuelve a leerla y acéptala."
        )
    if errors:
        raise ValidationError(errors)


def record_acceptance(
    *,
    user,
    terms_version: str,
    privacy_version: str,
    ip_address: str | None = None,
    user_agent: str = "",
) -> None:
    """Dejar constancia de que esa cuenta aceptó las versiones vigentes.

    Aceptar dos veces la misma versión no duplica la constancia.
    """
    check_versions(terms_version=terms_version, privacy_version=privacy_version)
    for kind, version in (
        (LegalDocumentKind.TERMS, terms_version),
        (LegalDocumentKind.PRIVACY, privacy_version),
    ):
        LegalAcceptance.objects.get_or_create(
            user=user,
            document=kind,
            version=version,
            defaults={
                "ip_address": ip_address or None,
                "user_agent": (user_agent or "")[:USER_AGENT_MAX],
            },
        )
    logger.info(
        "Legal documents accepted",
        extra={
            "user_id": str(user.pk),
            "terms": terms_version,
            "privacy": privacy_version,
        },
    )


def status_for(user) -> dict:
    """Qué versión rige, cuál aceptó la cuenta, y si le falta aceptar algo."""
    current = documents.current_versions()
    latest: dict[str, str] = {}
    for kind, version in user.legal_acceptances.order_by("-accepted_at").values_list(
        "document", "version"
    ):
        latest.setdefault(kind, version)
    accepted_current = set(
        user.legal_acceptances.filter(
            document__in=current.keys(),
        ).values_list("document", "version")
    )
    status: dict = {}
    for kind, version in current.items():
        status[kind] = {
            "version": version,
            "accepted_version": latest.get(kind),
        }
    status["pending"] = any(
        (kind, version) not in accepted_current for kind, version in current.items()
    )
    return status


def client_ip(request) -> str | None:
    """La dirección de quien hace la petición, detrás del proxy de la plataforma."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None
