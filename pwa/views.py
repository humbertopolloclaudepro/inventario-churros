import hmac

from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from inventario.permisos import GRUPO_VENDEDOR, es_admin


@login_required
@ensure_csrf_cookie
@never_cache
def app(request):
    return render(request, "pwa/app.html", {"es_admin": es_admin(request.user)})


class RegistroForm(UserCreationForm):
    """Cuenta nueva desde la app. Pide el código de la tienda para que no entre cualquiera con el APK."""

    codigo_tienda = forms.CharField()

    def clean_codigo_tienda(self):
        codigo = self.cleaned_data["codigo_tienda"].strip()
        if not hmac.compare_digest(codigo.lower(), settings.CODIGO_REGISTRO.lower()):
            raise forms.ValidationError("El código de la tienda no es correcto. Pídeselo al dueño.")
        return codigo


def registro(request):
    """Crea un usuario con rol Vendedor. Solo funciona si el servidor tiene CODIGO_REGISTRO."""
    abierto = bool(settings.CODIGO_REGISTRO)
    form = RegistroForm(request.POST or None) if abierto else None
    if abierto and request.method == "POST" and form.is_valid():
        with transaction.atomic():
            usuario = form.save()
            grupo, _ = Group.objects.get_or_create(name=GRUPO_VENDEDOR)
            usuario.groups.add(grupo)
        return redirect("/login/?creada=1")
    return render(request, "pwa/registro.html", {"form": form, "registro_abierto": abierto})


def manifest(request):
    return JsonResponse(
        {
            "name": "EasyStock · Inventario",
            "short_name": "EasyStock",
            "lang": "es-MX",
            "start_url": "/app/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#ffffff",
            "theme_color": "#4285f4",
            "icons": [
                {"src": static("pwa/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
                {"src": static("pwa/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
                {"src": static("pwa/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
        },
        content_type="application/manifest+json",
    )


@never_cache
def service_worker(request):
    # Se sirve desde la raíz para que pueda controlar /app/.
    return render(request, "pwa/sw.js", content_type="application/javascript")
