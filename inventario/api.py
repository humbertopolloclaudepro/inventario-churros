"""API REST que usa la app del celular (PWA)."""
from django.db.models import Prefetch, Q
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from catalogo.models import Categoria, Marca, ModeloTelefono, Variante

from .models import Existencia, Movimiento, Ubicacion
from .permisos import es_admin
from .serializers import (
    AltaRapidaSerializer,
    CategoriaSerializer,
    MarcaSerializer,
    ModeloTelefonoSerializer,
    MovimientoCrearSerializer,
    UbicacionSerializer,
    VarianteSerializer,
)
from .services import ErrorInventario, alta_rapida, registrar_movimiento


def variantes_qs():
    return (
        Variante.objects.filter(activo=True)
        .select_related("producto__categoria", "producto__modelo_telefono__marca")
        .prefetch_related(
            Prefetch(
                "existencias",
                queryset=Existencia.objects.filter(cantidad__gt=0).select_related("ubicacion"),
            )
        )
    )


def variante_data(request, pk):
    return VarianteSerializer(variantes_qs().get(pk=pk), context={"request": request}).data


@api_view(["GET"])
def yo(request):
    return Response({"usuario": request.user.get_username(), "es_admin": es_admin(request.user)})


@api_view(["GET"])
def buscar(request):
    """Busca por código exacto o por palabras: "mica s23 ultra"."""
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return Response([])
    qs = variantes_qs()
    exacto = qs.filter(codigo_barras__iexact=q)
    if exacto.exists():
        qs = exacto
    else:
        for palabra in q.split():
            qs = qs.filter(
                Q(producto__nombre__icontains=palabra)
                | Q(producto__modelo_telefono__nombre__icontains=palabra)
                | Q(producto__modelo_telefono__marca__nombre__icontains=palabra)
                | Q(producto__categoria__nombre__icontains=palabra)
                | Q(color__icontains=palabra)
                | Q(material__icontains=palabra)
            )
    return Response(VarianteSerializer(qs[:30], many=True, context={"request": request}).data)


@api_view(["GET"])
def por_codigo(request):
    """Resuelve un código escaneado: variante, ubicación o desconocido."""
    codigo = request.query_params.get("c", "").strip()
    variante = variantes_qs().filter(codigo_barras__iexact=codigo).first() if codigo else None
    if variante:
        return Response({
            "tipo": "variante",
            "variante": VarianteSerializer(variante, context={"request": request}).data,
        })
    ubicacion = Ubicacion.objects.filter(codigo__iexact=codigo, activo=True).first() if codigo else None
    if ubicacion:
        contenido = (
            Existencia.objects.filter(ubicacion=ubicacion, cantidad__gt=0)
            .select_related("variante__producto__modelo_telefono__marca")
        )
        return Response({
            "tipo": "ubicacion",
            "ubicacion": UbicacionSerializer(ubicacion).data,
            "contenido": [
                {"variante_id": e.variante_id, "descripcion": str(e.variante), "cantidad": e.cantidad}
                for e in contenido
            ],
        })
    return Response({"tipo": "desconocido", "codigo": codigo}, status=status.HTTP_404_NOT_FOUND)


@api_view(["GET"])
def catalogo(request):
    """Opciones para los selectores en cascada del alta rápida."""
    return Response({
        "categorias": CategoriaSerializer(Categoria.objects.all(), many=True).data,
        "marcas": MarcaSerializer(Marca.objects.all(), many=True).data,
        "modelos": ModeloTelefonoSerializer(ModeloTelefono.objects.all(), many=True).data,
    })


def _crear_simple(request, serializer_cls, model, campos):
    """get_or_create para el botón "+ Nuevo" de los selectores."""
    datos = {c: request.data.get(c) for c in campos}
    nombre = (datos.get("nombre") or "").strip()
    if not nombre:
        return Response({"detail": "Escribe un nombre."}, status=status.HTTP_400_BAD_REQUEST)
    datos["nombre"] = nombre
    s = serializer_cls(data=datos)
    lookup = {"nombre__iexact": nombre}
    if "marca" in campos:
        lookup["marca_id"] = datos.get("marca")
    existente = model.objects.filter(**lookup).first()
    if existente:
        return Response(serializer_cls(existente).data, status=status.HTTP_200_OK)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def crear_categoria(request):
    return _crear_simple(request, CategoriaSerializer, Categoria, ["nombre"])


@api_view(["POST"])
def crear_marca(request):
    return _crear_simple(request, MarcaSerializer, Marca, ["nombre"])


@api_view(["POST"])
def crear_modelo(request):
    return _crear_simple(request, ModeloTelefonoSerializer, ModeloTelefono, ["marca", "nombre"])


@api_view(["GET"])
def ubicaciones(request):
    return Response(UbicacionSerializer(Ubicacion.objects.filter(activo=True), many=True).data)


@api_view(["POST"])
def crear_movimiento(request):
    s = MovimientoCrearSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    if d["tipo"] == Movimiento.Tipo.AJUSTE and not es_admin(request.user):
        return Response({"detail": "Solo un administrador puede hacer ajustes."}, status=status.HTTP_403_FORBIDDEN)
    try:
        mov = registrar_movimiento(usuario=request.user, **d)
    except ErrorInventario as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(
        {"movimiento": mov.pk, "variante": variante_data(request, mov.variante_id)},
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
def crear_alta_rapida(request):
    s = AltaRapidaSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = dict(s.validated_data)
    if not es_admin(request.user):
        d["costo"] = 0  # Los vendedores no capturan ni ven costos.
    try:
        variante = alta_rapida(usuario=request.user, **d)
    except ErrorInventario as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"variante": variante_data(request, variante.pk)}, status=status.HTTP_201_CREATED)
