"""Leads views: receiving a message from the public page."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from apps.leads.serializers import LeadSerializer
from apps.legal.services import client_ip
from common.recaptcha import Verdict, guard_public_form
from common.views import TenantAPIView

logger = logging.getLogger("apps")


class ContactView(TenantAPIView):
    """POST /api/contact/ — dejar un mensaje sin tener cuenta."""

    # Público: no lee la sesión. Una cookie de otra visita (viva sin X-CSRFToken,
    # o vencida) no lo vuelve un 403 de CSRF ni un 401 (iteracion-27 #7).
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_scope = "contact"

    def post(self, request: Request) -> Response:
        # Si Google no contesta, el mensaje se queda —bajo el límite estricto de
        # contacto— marcado para revisar: perder un cliente cuesta más.
        verdict = guard_public_form(
            request,
            action="contact_submit",
            when_unavailable="review",
            remote_ip=client_ip(request),
        )
        received = Response(
            {"detail": "Gracias. Te contactamos pronto."},
            status=status.HTTP_201_CREATED,
        )
        if verdict is Verdict.DROP:
            return received

        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save(needs_review=verdict is Verdict.REVIEW)
        logger.info("Contact lead received", extra={"lead_id": str(lead.pk)})
        return received
