"""API REST que usa la app del celular (PWA)."""
from django.db.models import F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from catalogo.fotos import FotoInvalida, preparar_foto
from catalogo.models import Categoria, FotoVariante, Marca, ModeloTelefono, Variante

from . import auditorias as aud
from .models import Auditoria, Existencia, Movimiento, Ubicacion
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
        .annotate(foto_actualizada=F("foto__actualizada"))
        .prefetch_related(
            Prefetch(
                "existencias",
                queryset=Existencia.objects.filter(cantidad__gt=0).select_related("ubicacion"),
            )
        )
    )


def variante_data(request, pk):
    return VarianteSerializer(variantes_qs().get(pk=pk), context={"request": request}).data


def filtrar_texto(qs, q):
    """Código exacto o palabras sueltas: "mica s23 ultra" o "cajonera 2"."""
    exacto = qs.filter(codigo_barras__iexact=q)
    if exacto.exists():
        return exacto
    for palabra in q.split():
        qs = qs.filter(
            Q(producto__nombre__icontains=palabra)
            | Q(producto__modelo_telefono__nombre__icontains=palabra)
            | Q(producto__modelo_telefono__marca__nombre__icontains=palabra)
            | Q(producto__categoria__nombre__icontains=palabra)
            | Q(color__icontains=palabra)
            | Q(material__icontains=palabra)
            | Q(pk__in=Existencia.objects.filter(cantidad__gt=0, ubicacion__zona__icontains=palabra).values("variante"))
        )
    return qs


@api_view(["GET"])
def yo(request):
    return Response({"usuario": request.user.get_username(), "es_admin": es_admin(request.user)})


@api_view(["GET"])
def buscar(request):
    """Busca por código exacto o por palabras: "mica s23 ultra"."""
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return Response([])
    qs = filtrar_texto(variantes_qs(), q)
    return Response(VarianteSerializer(qs[:30], many=True, context={"request": request}).data)


ORDENES = {
    "nombre": ["producto__nombre", "producto__modelo_telefono__nombre", "color"],
    "-nombre": ["-producto__nombre", "-producto__modelo_telefono__nombre", "-color"],
    "cantidad": ["stock", "producto__nombre"],
    "-cantidad": ["-stock", "producto__nombre"],
    "reciente": ["-creado"],
}
LIMITE_INVENTARIO = 300


@api_view(["GET"])
def inventario(request):
    """Lista de la pantalla principal: todo el inventario, con filtro opcional y orden."""
    stock = (
        Existencia.objects.filter(variante=OuterRef("pk"))
        .values("variante")
        .annotate(total=Sum("cantidad"))
        .values("total")
    )
    qs = variantes_qs().annotate(stock=Coalesce(Subquery(stock, output_field=IntegerField()), Value(0)))
    q = request.query_params.get("q", "").strip()
    if q:
        qs = filtrar_texto(qs, q)
    orden = request.query_params.get("orden", "nombre")
    qs = qs.order_by(*ORDENES.get(orden, ORDENES["nombre"]))
    total = qs.count()
    datos = VarianteSerializer(qs[:LIMITE_INVENTARIO], many=True, context={"request": request}).data
    return Response({"total": total, "variantes": datos})


@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
def foto_variante(request, pk):
    """GET: la imagen. POST: sube o reemplaza la foto (campo "foto")."""
    variante = get_object_or_404(Variante, pk=pk)
    if request.method == "GET":
        foto = get_object_or_404(FotoVariante, variante=variante)
        respuesta = HttpResponse(bytes(foto.datos), content_type="image/jpeg")
        # La URL cambia cuando cambia la foto (?v=...), así que se puede guardar mucho tiempo.
        respuesta["Cache-Control"] = "private, max-age=2592000"
        return respuesta

    archivo = request.FILES.get("foto")
    if not archivo:
        return Response({"detail": "Elige o toma una foto."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        datos = preparar_foto(archivo)
    except FotoInvalida as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    FotoVariante.objects.update_or_create(
        variante=variante, defaults={"datos": datos, "subida_por": request.user}
    )
    return Response({"variante": variante_data(request, variante.pk)})


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


# ---------- Auditoría ----------


def _auditoria_data(request, auditoria):
    """Detalle para la app. Mientras se cuenta es "a ciegas": no incluye el stock del sistema."""
    admin = es_admin(request.user)
    lineas = aud.lineas_auditoria(auditoria)
    mostrar_sistema = admin and auditoria.estado == Auditoria.Estado.REVISION
    datos_lineas = []
    for l in lineas:
        d = {
            "variante_id": l["variante"].pk,
            "descripcion": str(l["variante"]),
            "codigo": l["variante"].codigo_barras,
            "ubicacion_id": l["ubicacion"].pk,
            "ubicacion": str(l["ubicacion"]),
            "contado": l["contado"],
            "contada": l["contada"],
        }
        if mostrar_sistema:
            d.update(sistema=l["sistema"], diferencia=l["diferencia"])
        datos_lineas.append(d)
    r = aud.resumen(lineas)
    if not mostrar_sistema:
        r = {"lineas": r["lineas"], "contadas": r["contadas"]}
    if auditoria.estado == Auditoria.Estado.APLICADA:
        r = {"lineas": auditoria.lineas, "contadas": auditoria.lineas,
             "con_diferencia": auditoria.lineas_con_diferencia,
             "faltantes": auditoria.piezas_faltantes, "sobrantes": auditoria.piezas_sobrantes}
    return {
        "id": auditoria.pk,
        "zona": auditoria.zona,
        "estado": auditoria.estado,
        "estado_texto": auditoria.get_estado_display(),
        "creada": timezone.localtime(auditoria.creada).strftime("%d/%m/%Y %H:%M"),
        "creada_por": auditoria.creada_por.get_username(),
        "minutos": auditoria.minutos,
        "es_admin": admin,
        "ubicaciones": UbicacionSerializer(
            Ubicacion.objects.filter(zona=auditoria.zona, activo=True), many=True
        ).data,
        "lineas": datos_lineas,
        "resumen": r,
    }


def _ejecutar(request, auditoria, funcion, solo_admin=False):
    if solo_admin and not es_admin(request.user):
        return Response({"detail": "Solo un administrador puede hacer eso."}, status=status.HTTP_403_FORBIDDEN)
    try:
        resultado = funcion(auditoria=auditoria, usuario=request.user)
    except ErrorInventario as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(resultado, tuple):
        resultado = resultado[0]
    resultado.refresh_from_db()
    return Response(_auditoria_data(request, resultado))


@api_view(["GET", "POST"])
def auditorias(request):
    if request.method == "POST":
        try:
            a = aud.iniciar_auditoria(zona=request.data.get("zona"), usuario=request.user)
        except ErrorInventario as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_auditoria_data(request, a), status=status.HTTP_201_CREATED)
    en_curso = Auditoria.objects.filter(estado__in=aud.EN_CURSO).select_related("creada_por")
    return Response({
        "zonas": aud.zonas_disponibles(),
        "en_curso": [
            {"id": a.pk, "zona": a.zona, "estado": a.estado, "estado_texto": a.get_estado_display(),
             "creada": timezone.localtime(a.creada).strftime("%d/%m %H:%M"), "creada_por": a.creada_por.get_username()}
            for a in en_curso
        ],
    })


@api_view(["GET"])
def auditoria_detalle(request, pk):
    return Response(_auditoria_data(request, get_object_or_404(Auditoria, pk=pk)))


@api_view(["POST"])
def auditoria_conteo(request, pk):
    auditoria = get_object_or_404(Auditoria, pk=pk)
    variante = aud.variante_por_id(request.data.get("variante"))
    ubicacion = Ubicacion.objects.filter(pk=request.data.get("ubicacion"), activo=True).first()
    if not variante or not ubicacion:
        return Response({"detail": "Producto o ubicación no válidos."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        sumar = request.data.get("sumar")
        fijar = request.data.get("fijar")
        conteo = aud.registrar_conteo(
            auditoria=auditoria, variante=variante, ubicacion=ubicacion, usuario=request.user,
            sumar=int(sumar) if sumar is not None else None,
            fijar=int(fijar) if fijar is not None else None,
        )
    except (TypeError, ValueError):
        return Response({"detail": "La cantidad debe ser un número entero."}, status=status.HTTP_400_BAD_REQUEST)
    except ErrorInventario as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"descripcion": str(variante), "ubicacion": str(ubicacion), "contado": conteo.contado})


@api_view(["POST"])
def auditoria_terminar(request, pk):
    return _ejecutar(request, get_object_or_404(Auditoria, pk=pk), aud.terminar_conteo)


@api_view(["POST"])
def auditoria_reabrir(request, pk):
    return _ejecutar(request, get_object_or_404(Auditoria, pk=pk), aud.reabrir_auditoria, solo_admin=True)


@api_view(["POST"])
def auditoria_aplicar(request, pk):
    return _ejecutar(request, get_object_or_404(Auditoria, pk=pk), aud.aplicar_auditoria, solo_admin=True)


@api_view(["POST"])
def auditoria_cancelar(request, pk):
    return _ejecutar(request, get_object_or_404(Auditoria, pk=pk), aud.cancelar_auditoria, solo_admin=True)
