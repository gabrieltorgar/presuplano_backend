"""Leads (contacto público) URLs."""

from django.urls import path

from apps.leads.views import ContactView

app_name = "leads"

urlpatterns = [
    path("contact/", ContactView.as_view(), name="contact"),
]
