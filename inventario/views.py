from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import HttpResponse
from django.utils import timezone

from catalogo.models import Variante

from .models import Existencia
from .permisos import es_admin
from .reportes import generar_reporte_inventario

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
