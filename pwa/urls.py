from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(url="/app/", permanent=False)),
    path("app/", views.app, name="app"),
    # Cada usuario cambia su propia contraseña (Django ya pide inicio de sesión y la mantiene activa).
    path(
        "cuenta/contrasena/",
        auth_views.PasswordChangeView.as_view(
            template_name="pwa/cambiar_contrasena.html",
            success_url=reverse_lazy("contrasena-cambiada"),
        ),
        name="cambiar-contrasena",
    ),
    path(
        "cuenta/contrasena/listo/",
        auth_views.PasswordChangeDoneView.as_view(template_name="pwa/contrasena_cambiada.html"),
        name="contrasena-cambiada",
    ),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service-worker"),
]
