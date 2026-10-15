from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie

from inventario.permisos import es_admin


@login_required
@ensure_csrf_cookie
@never_cache
def app(request):
    return render(request, "pwa/app.html", {"es_admin": es_admin(request.user)})


def manifest(request):
    return JsonResponse(
        {
            "name": "Los Churros Rellenos · Inventario",
            "short_name": "Inventario",
            "lang": "es-MX",
            "start_url": "/app/",
            "scope": "/",
            "display": "standalone",
            "orientation": "portrait",
            "background_color": "#ffffff",
            "theme_color": "#b45309",
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
