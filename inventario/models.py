"""Ubicaciones físicas, stock por ubicación y registro inmutable de movimientos.

Regla de oro: el stock (Existencia) SOLO cambia a través de
inventario.services.registrar_movimiento, que crea el Movimiento y actualiza la
Existencia en la misma transacción.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from catalogo.models import Variante


def generar_codigo_ubicacion():
    return "UBI-" + uuid.uuid4().hex[:8].upper()


class Ubicacion(models.Model):
    """La coordenada física: "Cajonera 2 · Nivel B · Caja Azul"."""

    zona = models.CharField(max_length=60, help_text='Mueble o área, p. ej. "Cajonera 2" o "Estante A".')
    nivel = models.CharField(max_length=20, blank=True)
    caja = models.CharField(max_length=40, blank=True)
    codigo = models.CharField("código QR", max_length=32, unique=True, default=generar_codigo_ubicacion)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["zona", "nivel", "caja"]
        verbose_name = "ubicación"
        verbose_name_plural = "ubicaciones"
        constraints = [
            models.UniqueConstraint(fields=["zona", "nivel", "caja"], name="ubicacion_unica"),
        ]

    def __str__(self):
        partes = [self.zona, f"Nivel {self.nivel}" if self.nivel else "", self.caja]
        return " · ".join(p for p in partes if p)


class Existencia(models.Model):
    """Cuántas piezas de una variante hay en una ubicación."""

    variante = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="existencias")
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT, related_name="existencias")
    cantidad = models.IntegerField(default=0)

    class Meta:
        ordering = ["ubicacion__zona", "ubicacion__nivel", "ubicacion__caja"]
        constraints = [
            models.UniqueConstraint(fields=["variante", "ubicacion"], name="existencia_unica"),
            models.CheckConstraint(condition=models.Q(cantidad__gte=0), name="existencia_no_negativa"),
        ]

    def __str__(self):
        return f"{self.variante} en {self.ubicacion}: {self.cantidad}"


class Movimiento(models.Model):
    """Registro inmutable. Los errores se corrigen con un nuevo movimiento de ajuste."""

    class Tipo(models.TextChoices):
        ENTRADA = "entrada", "Entrada"
        SALIDA = "salida", "Salida"
        AJUSTE = "ajuste", "Ajuste"

    class Motivo(models.TextChoices):
        # Entradas
        COMPRA = "compra", "Compra a proveedor"
        DEVOLUCION_CLIENTE = "devolucion_cliente", "Devolución de cliente"
        ALTA = "alta", "Alta de producto"
        # Salidas (sin montos: la app controla inventario, no ventas)
        VENTA = "venta", "Venta"
        MERMA = "merma", "Merma o daño"
        DEVOLUCION_PROVEEDOR = "devolucion_proveedor", "Devolución a proveedor"
        # Ajustes (solo administradores)
        CONTEO = "conteo", "Conteo físico"
        CORRECCION = "correccion", "Corrección de captura"

    variante = models.ForeignKey(Variante, on_delete=models.PROTECT, related_name="movimientos")
    ubicacion = models.ForeignKey(Ubicacion, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    motivo = models.CharField(max_length=25, choices=Motivo.choices)
    cantidad = models.IntegerField(help_text="Positiva en entradas y salidas; con signo en ajustes.")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos")
    fecha = models.DateTimeField(default=timezone.now, db_index=True)
    nota = models.CharField(max_length=200, blank=True)
    uuid_cliente = models.UUIDField(
        null=True, blank=True, unique=True, editable=False,
        help_text="Lo genera la app; evita registrar dos veces el mismo movimiento al sincronizar.",
    )

    class Meta:
        ordering = ["-fecha"]
        indexes = [models.Index(fields=["variante", "tipo", "motivo", "fecha"])]

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad} × {self.variante} ({self.ubicacion})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los movimientos no se modifican; registra un ajuste.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los movimientos no se eliminan; registra un ajuste.")
