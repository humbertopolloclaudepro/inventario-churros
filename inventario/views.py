from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from catalogo.models import Variante

from .importacion import ErrorArchivo, importar_filas, leer_archivo, plantilla_xlsx
from .models import Existencia
from .permisos import es_admin
from .reportes import generar_reporte_inventario

SESION_IMPORTACION = "importacion_pendiente"

MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def filas_reporte():
    """Variantes activas con sus ubicaciones, ordenadas por categoría, en el formato de reportes.py."""
    existencias = (
        Existencia.objects.filter(cantidad__gt=0)
        .select_related("ubicacion")
        .order_by("ubicacion__zona", "ubicacion__nivel", "ubicacion__caja")
    )
    variantes = (
        Variante.objects.filter(activo=True)
        .select_related("producto__categoria", "producto__modelo_telefono__marca")
        .prefetch_related(Prefetch("existencias", queryset=existencias))
        .order_by(
            "producto__categoria__nombre",
            "producto__modelo_telefono__marca__nombre",
            "producto__modelo_telefono__nombre",
            "producto__nombre",
            "color",
            "material",
        )
    )
    return [
        {
            "categoria": v.producto.categoria.nombre,
            "marca": v.producto.modelo_telefono.marca.nombre,
            "modelo": v.producto.modelo_telefono.nombre,
            "producto": v.producto.nombre,
            "color": v.color,
            "material": v.material,
            "codigo": v.codigo_barras,
            "precio": v.precio,
            "costo": v.costo,
            "stock_minimo": v.stock_minimo,
            "ubicaciones": [(str(e.ubicacion), e.cantidad) for e in v.existencias.all()],
        }
        for v in variantes
    ]


@login_required
def reporte_inventario(request):
    """PDF del inventario actual por categoría. Los costos solo se muestran a administradores."""
    ahora = timezone.localtime()
    fecha = f"{ahora.day} {MESES[ahora.month - 1]} {ahora.year}, {ahora:%H:%M}"
    pdf = generar_reporte_inventario(
        filas_reporte(),
        generado_por=request.user.get_username(),
        fecha_texto=fecha,
        mostrar_costos=es_admin(request.user),
    )
    respuesta = HttpResponse(pdf, content_type="application/pdf")
    respuesta["Content-Disposition"] = f'inline; filename="inventario-{ahora:%Y-%m-%d}.pdf"'
    return respuesta


@staff_member_required
def importar_inventario(request):
    """Paso 1: subir y revisar el archivo (sin guardar). Paso 2: confirmar y guardar."""
    if not es_admin(request.user):
        raise PermissionDenied
    contexto = {**admin.site.each_context(request), "title": "Importar inventario"}

    if request.method == "POST" and request.POST.get("accion") == "confirmar":
        pendiente = request.session.pop(SESION_IMPORTACION, None)
        if not pendiente:
            messages.error(request, "No hay un archivo revisado para importar. Súbelo de nuevo.")
            return redirect("importar-inventario")
        resultado = importar_filas(pendiente["filas"], usuario=request.user, guardar=True)
        if resultado.guardado:
            messages.success(
                request,
                f"Inventario importado: {resultado.variantes_nuevas} productos nuevos, "
                f"{resultado.ubicaciones_nuevas} ubicaciones nuevas y {resultado.piezas} piezas.",
            )
            return redirect("admin:catalogo_variante_changelist")
        contexto.update(resultado=resultado, nombre_archivo=pendiente["nombre"])

    elif request.method == "POST":
        request.session.pop(SESION_IMPORTACION, None)
        archivo = request.FILES.get("archivo")
        if not archivo:
            contexto["error_archivo"] = "Elige un archivo para subir."
        else:
            try:
                filas = leer_archivo(archivo.name, archivo.read())
            except ErrorArchivo as e:
                contexto["error_archivo"] = str(e)
            else:
                resultado = importar_filas(filas, usuario=request.user, guardar=False)
                contexto.update(resultado=resultado, nombre_archivo=archivo.name)
                if not resultado.errores:
                    # Se guarda lo revisado para que "Confirmar" importe exactamente esto.
                    request.session[SESION_IMPORTACION] = {"nombre": archivo.name, "filas": filas}

    return render(request, "admin/importar_inventario.html", contexto)


@staff_member_required
def plantilla_importacion(request):
    respuesta = HttpResponse(
        plantilla_xlsx(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    respuesta["Content-Disposition"] = 'attachment; filename="plantilla_inventario.xlsx"'
    return respuesta
