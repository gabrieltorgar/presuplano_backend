"""Root URL configuration."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.admin_login import admin_login

urlpatterns = [
    # Primero el login del admin con su límite de intentos: el de Django, detrás.
    path("admin/login/", admin_login),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]

# Servir archivos media y static en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
