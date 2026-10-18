from django import forms
from django.contrib import admin, messages
from django.db.models import Sum
from django.http import HttpResponse

from .etiquetas import generar_pdf
from .models import Auditoria, ConteoAuditoria, Existencia, Movimiento, Ubicacion
from .services import MOTIVOS_POR_TIPO, ErrorInventario, registrar_movimiento


@admin.action(description="Imprimir etiquetas QR (PDF)")
def imprimir_etiquetas_ubicaciones(modeladmin, request, queryset):
    etiquetas = [(u.codigo, str(u), "Ubicación") for u in queryset]
    respuesta = HttpResponse(generar_pdf(etiquetas), content_type="application/pdf")
    respuesta["Content-Disposition"] = 'inline; filename="etiquetas-ubicaciones.pdf"'
    return respuesta


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "codigo", "piezas", "activo"]
    list_filter = ["zona", "activo"]
    search_fields = ["zona", "nivel", "caja", "codigo"]
    actions = [imprimir_etiquetas_ubicaciones]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(total_piezas=Sum("existencias__cantidad"))

    @admin.display(description="piezas", ordering="total_piezas")
    def piezas(self, obj):
        return obj.total_piezas or 0


@admin.register(Existencia)
class ExistenciaAdmin(admin.ModelAdmin):
    """Solo lectura: el stock cambia registrando movimientos."""

    list_display = ["variante", "ubicacion", "cantidad"]
    list_filter = ["ubicacion__zona", "variante__producto__categoria"]
    search_fields = ["variante__codigo_barras", "variante__producto__nombre", "variante__producto__modelo_telefono__nombre"]
    list_select_related = ["variante__producto__modelo_telefono__marca", "ubicacion"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class MovimientoAdminForm(forms.ModelForm):
    class Meta:
        model = Movimiento
        fields = ["variante", "ubicacion", "tipo", "motivo", "cantidad", "nota"]

    def clean(self):
        datos = super().clean()
        tipo, motivo = datos.get("tipo"), datos.get("motivo")
        if tipo and motivo and motivo not in MOTIVOS_POR_TIPO[tipo]:
            raise forms.ValidationError("Ese motivo no corresponde al tipo de movimiento elegido.")
        variante, ubicacion, cantidad = datos.get("variante"), datos.get("ubicacion"), datos.get("cantidad")
        if variante and ubicacion and cantidad is not None and tipo:
            delta = -cantidad if tipo == Movimiento.Tipo.SALIDA else cantidad
            actual = (
                Existencia.objects.filter(variante=variante, ubicacion=ubicacion)
                .values_list("cantidad", flat=True)
                .first()
                or 0
            )
            if actual + delta < 0:
                raise forms.ValidationError(f"Solo hay {actual} pza(s) en esa ubicación.")
        return datos


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    """Historial inmutable. Desde aquí se pueden registrar movimientos nuevos (p. ej. ajustes)."""

    form = MovimientoAdminForm
    list_display = ["fecha", "tipo", "motivo", "variante", "ubicacion", "cantidad", "usuario"]
    list_filter = ["tipo", "motivo", "usuario", "ubicacion__zona"]
    search_fields = ["variante__codigo_barras", "variante__producto__nombre", "nota"]
    date_hierarchy = "fecha"
    autocomplete_fields = ["variante"]
    list_select_related = ["variante__producto__modelo_telefono__marca", "ubicacion", "usuario"]

    def has_change_permission(self, request, obj=None):
        return obj is None and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        try:
            mov = registrar_movimiento(
                variante=obj.variante,
                ubicacion=obj.ubicacion,
                tipo=obj.tipo,
                motivo=obj.motivo,
                cantidad=obj.cantidad,
                usuario=request.user,
                nota=obj.nota,
            )
        except ErrorInventario as e:
            self.message_user(request, str(e), level=messages.ERROR)
            raise
        obj.pk = mov.pk
        obj._state.adding = False


class ConteoInline(admin.TabularInline):
    model = ConteoAuditoria
    fields = ["ubicacion", "variante", "contado", "actualizado_por", "actualizado"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Auditoria)
class AuditoriaAdmin(admin.ModelAdmin):
    """Historial de auditorías. Se hacen desde la app (pestaña Auditar)."""

    list_display = ["creada", "zona", "estado", "creada_por", "duracion", "exactitud_col", "piezas_faltantes", "piezas_sobrantes"]
    list_filter = ["estado", "zona"]
    date_hierarchy = "creada"
    readonly_fields = [
        "zona", "estado", "creada_por", "creada", "terminada", "duracion", "aplicada_por", "aplicada",
        "lineas", "lineas_con_diferencia", "exactitud_col", "piezas_faltantes", "piezas_sobrantes",
    ]
    fields = readonly_fields
    inlines = [ConteoInline]

    @admin.display(description="duración del conteo")
    def duracion(self, obj):
        return f"{obj.minutos} min" if obj.minutos is not None else "—"

    @admin.display(description="exactitud")
    def exactitud_col(self, obj):
        return f"{obj.exactitud} %" if obj.exactitud is not None else "—"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
