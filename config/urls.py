from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from inventario import views as inventario_views

admin.site.site_header = "Los Churros Rellenos · Inventario"
admin.site.site_title = "Inventario"
admin.site.index_title = "Panel del dueño"
admin.site.index_template = "admin/index_churros.html"  # agrega la sección de Herramientas

urlpatterns = [
    # Antes de admin.site.urls para que estas rutas del panel no las tome el admin.
    path("admin/importar/", inventario_views.importar_inventario, name="importar-inventario"),
    path("admin/importar/plantilla.xlsx", inventario_views.plantilla_importacion, name="plantilla-importacion"),
    path("admin/", admin.site.urls),
    path("reportes/inventario.pdf", inventario_views.reporte_inventario, name="reporte-inventario"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/", include("inventario.api_urls")),
    path("", include("pwa.urls")),
]
