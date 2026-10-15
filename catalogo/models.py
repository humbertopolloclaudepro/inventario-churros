"""Catálogo multivariante: Categoría > Marca > Modelo de teléfono > Producto > Variante.

La Variante es el SKU: lo que se escanea, se ubica y se mueve.
"""
import uuid

from django.conf import settings
from django.db import models


def generar_codigo_variante():
    """Código propio para mercancía que llega sin código de barras de fábrica."""
    return "CR" + uuid.uuid4().hex[:10].upper()


class Categoria(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"

    def __str__(self):
        return self.nombre


class Marca(models.Model):
    nombre = models.CharField(max_length=60, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class ModeloTelefono(models.Model):
    marca = models.ForeignKey(Marca, on_delete=models.PROTECT, related_name="modelos")
    nombre = models.CharField(max_length=80, help_text='Nombre exacto, p. ej. "iPhone 14 Pro" o "Galaxy S23 Ultra".')
    fecha_lanzamiento = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["marca__nombre", "nombre"]
        verbose_name = "modelo de teléfono"
        verbose_name_plural = "modelos de teléfono"
        constraints = [
            models.UniqueConstraint(fields=["marca", "nombre"], name="modelo_unico_por_marca"),
        ]

    def __str__(self):
        return f"{self.marca} {self.nombre}"


class Producto(models.Model):
    """El diseño base, p. ej. "Funda uso rudo" para el iPhone 14."""

    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="productos")
    modelo_telefono = models.ForeignKey(ModeloTelefono, on_delete=models.PROTECT, related_name="productos")
    nombre = models.CharField(max_length=120)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["modelo_telefono__marca__nombre", "modelo_telefono__nombre", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["categoria", "modelo_telefono", "nombre"], name="producto_unico"
            ),
        ]

    def __str__(self):
        return f"{self.nombre} {self.modelo_telefono}"


class Variante(models.Model):
    """El SKU: un producto en un color o material concreto."""

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="variantes")
    color = models.CharField(max_length=40, blank=True)
    material = models.CharField(max_length=40, blank=True)
    codigo_barras = models.CharField(
        "código", max_length=64, unique=True, default=generar_codigo_variante,
        help_text="UPC/EAN de fábrica o un código propio generado por el sistema.",
    )
    precio = models.DecimalField("precio de venta", max_digits=10, decimal_places=2, default=0)
    costo = models.DecimalField(
        "costo de proveedor", max_digits=10, decimal_places=2, default=0,
        help_text="Solo lo ven los administradores. Se usa para calcular el capital atorado.",
    )
    stock_minimo = models.PositiveIntegerField("stock mínimo", default=0)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["producto__modelo_telefono__nombre", "producto__nombre", "color"]

    def __str__(self):
        detalle = " ".join(p for p in [self.color, self.material] if p)
        return f"{self.producto} · {detalle}" if detalle else str(self.producto)
