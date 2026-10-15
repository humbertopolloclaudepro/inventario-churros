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
]
