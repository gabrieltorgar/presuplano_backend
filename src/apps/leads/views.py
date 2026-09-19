"""Leads views: receiving a message from the public page."""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.leads.serializers import LeadSerializer

logger = logging.getLogger("apps")


class ContactView(APIView):
    """POST /api/contact/ — dejar un mensaje sin tener cuenta."""

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = serializer.save()
        logger.info("Contact lead received", extra={"lead_id": str(lead.pk)})
        return Response(
            {"detail": "Gracias. Te contactamos pronto."},
            status=status.HTTP_201_CREATED,
        )
