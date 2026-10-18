from django.urls import path

from . import api

urlpatterns = [
    path("yo/", api.yo, name="api-yo"),
    path("buscar/", api.buscar, name="api-buscar"),
    path("codigo/", api.por_codigo, name="api-codigo"),
    path("catalogo/", api.catalogo, name="api-catalogo"),
    path("categorias/", api.crear_categoria, name="api-crear-categoria"),
    path("marcas/", api.crear_marca, name="api-crear-marca"),
    path("modelos/", api.crear_modelo, name="api-crear-modelo"),
    path("ubicaciones/", api.ubicaciones, name="api-ubicaciones"),
    path("movimientos/", api.crear_movimiento, name="api-movimientos"),
    path("alta-rapida/", api.crear_alta_rapida, name="api-alta-rapida"),
    path("auditorias/", api.auditorias, name="api-auditorias"),
    path("auditorias/<int:pk>/", api.auditoria_detalle, name="api-auditoria"),
    path("auditorias/<int:pk>/conteo/", api.auditoria_conteo, name="api-auditoria-conteo"),
    path("auditorias/<int:pk>/terminar/", api.auditoria_terminar, name="api-auditoria-terminar"),
    path("auditorias/<int:pk>/reabrir/", api.auditoria_reabrir, name="api-auditoria-reabrir"),
    path("auditorias/<int:pk>/aplicar/", api.auditoria_aplicar, name="api-auditoria-aplicar"),
    path("auditorias/<int:pk>/cancelar/", api.auditoria_cancelar, name="api-auditoria-cancelar"),
]
