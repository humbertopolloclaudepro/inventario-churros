"""Panel del dueño para el catálogo, con el radar de obsolescencia y la alerta de stock bajo."""
from datetime import timedelta

from django.contrib import admin
from django.db.models import DecimalField, ExpressionWrapper, F, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from inventario.etiquetas import generar_pdf
from inventario.models import Existencia, Movimiento

from .models import Categoria, Marca, ModeloTelefono, Producto, Variante


def anotar_variantes(qs):
    """Agrega stock total, última venta y capital (costo × stock) a cada variante.

    Se usan subconsultas para no multiplicar filas al cruzar existencias y movimientos.
    """
    stock = (
        Existencia.objects.filter(variante=OuterRef("pk"))
        .values("variante")
        .annotate(total=Sum("cantidad"))
        .values("total")
    )
    ultima_venta = (
        Movimiento.objects.filter(
            variante=OuterRef("pk"),
            tipo=Movimiento.Tipo.SALIDA,
            motivo=Movimiento.Motivo.VENTA,
        )
        .order_by("-fecha")
        .values("fecha")[:1]
    )
    return qs.annotate(
        stock=Coalesce(Subquery(stock, output_field=IntegerField()), Value(0)),
        ultima_venta=Subquery(ultima_venta),
    ).annotate(
        ultima_actividad=Coalesce("ultima_venta", "creado"),
        capital=ExpressionWrapper(F("costo") * F("stock"), output_field=DecimalField(max_digits=12, decimal_places=2)),
    )


class RadarObsolescenciaFilter(admin.SimpleListFilter):
    title = "radar de obsolescencia"
    parameter_name = "sin_venta"

    def lookups(self, request, model_admin):
        return [("30", "Sin venta en 30+ días"), ("60", "Sin venta en 60+ días"), ("90", "Sin venta en 90+ días")]

    def queryset(self, request, queryset):
        if self.value() in {"30", "60", "90"}:
            limite = timezone.now() - timedelta(days=int(self.value()))
            return queryset.filter(stock__gt=0, ultima_actividad__lt=limite)
        return queryset


class StockBajoFilter(admin.SimpleListFilter):
    title = "stock"
    parameter_name = "stock"

    def lookups(self, request, model_admin):
        return [("bajo", "Por debajo del mínimo"), ("agotado", "Agotado")]

    def queryset(self, request, queryset):
        if self.value() == "bajo":
            return queryset.filter(stock_minimo__gt=0, stock__lt=F("stock_minimo"))
        if self.value() == "agotado":
            return queryset.filter(stock=0)
        return queryset


@admin.action(description="Imprimir etiquetas QR (PDF)")
def imprimir_etiquetas_variantes(modeladmin, request, queryset):
    etiquetas = [
        (v.codigo_barras, str(v.producto), " ".join(p for p in [v.color, v.material] if p))
        for v in queryset.select_related("producto__modelo_telefono__marca")
    ]
    respuesta = HttpResponse(generar_pdf(etiquetas), content_type="application/pdf")
    respuesta["Content-Disposition"] = 'inline; filename="etiquetas-productos.pdf"'
    return respuesta


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    search_fields = ["nombre"]


@admin.register(Marca)
class MarcaAdmin(admin.ModelAdmin):
    search_fields = ["nombre"]


@admin.register(ModeloTelefono)
class ModeloTelefonoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "marca", "fecha_lanzamiento"]
    list_filter = ["marca"]
    search_fields = ["nombre", "marca__nombre"]


class VarianteInline(admin.TabularInline):
    model = Variante
    extra = 0
    fields = ["color", "material", "codigo_barras", "precio", "costo", "stock_minimo", "activo"]


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "modelo_telefono", "categoria"]
    list_filter = ["categoria", "modelo_telefono__marca"]
    search_fields = ["nombre", "modelo_telefono__nombre", "modelo_telefono__marca__nombre"]
    autocomplete_fields = ["modelo_telefono"]
    inlines = [VarianteInline]


@admin.register(Variante)
class VarianteAdmin(admin.ModelAdmin):
    list_display = ["__str__", "codigo_barras", "precio", "stock_col", "minimo_col", "ultima_venta_col", "capital_col"]
    list_filter = [
        RadarObsolescenciaFilter,
        StockBajoFilter,
        "producto__categoria",
        "producto__modelo_telefono__marca",
        "activo",
    ]
    search_fields = [
        "codigo_barras", "color", "material", "producto__nombre",
        "producto__modelo_telefono__nombre", "producto__modelo_telefono__marca__nombre",
    ]
    autocomplete_fields = ["producto"]
    readonly_fields = ["creado", "creado_por"]
    actions = [imprimir_etiquetas_variantes]
    list_select_related = ["producto__modelo_telefono__marca", "producto__categoria"]

    def get_queryset(self, request):
        return anotar_variantes(super().get_queryset(request))

    @admin.display(description="stock", ordering="stock")
    def stock_col(self, obj):
        return obj.stock

    @admin.display(description="mínimo", ordering="stock_minimo")
    def minimo_col(self, obj):
        return obj.stock_minimo or "—"

    @admin.display(description="última venta", ordering="ultima_venta")
    def ultima_venta_col(self, obj):
        if not obj.ultima_venta:
            return "Nunca"
        dias = (timezone.now() - obj.ultima_venta).days
        return "Hoy" if dias == 0 else f"Hace {dias} día(s)"

    @admin.display(description="capital atorado", ordering="capital")
    def capital_col(self, obj):
        return f"${obj.capital:,.2f}"

    def save_model(self, request, obj, form, change):
        if not change and not obj.creado_por_id:
            obj.creado_por = request.user
        super().save_model(request, obj, form, change)
