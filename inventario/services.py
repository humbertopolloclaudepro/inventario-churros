"""Reglas de inventario. Todo cambio de stock pasa por aquí."""
from decimal import Decimal

from django.db import transaction

from catalogo.models import Producto, Variante, generar_codigo_variante

from .models import Existencia, Movimiento

T = Movimiento.Tipo
M = Movimiento.Motivo

MOTIVOS_POR_TIPO = {
    T.ENTRADA: {M.COMPRA, M.DEVOLUCION_CLIENTE, M.ALTA},
    T.SALIDA: {M.VENTA, M.MERMA, M.DEVOLUCION_PROVEEDOR},
    T.AJUSTE: {M.CONTEO, M.CORRECCION},
}


class ErrorInventario(Exception):
    """Error de negocio con un mensaje listo para mostrar al usuario."""


@transaction.atomic
def registrar_movimiento(*, variante, ubicacion, tipo, motivo, cantidad, usuario, nota="", uuid_cliente=None):
    """Crea el movimiento y actualiza la existencia en una sola transacción.

    Si llega un uuid_cliente que ya se registró, devuelve el movimiento existente
    sin repetirlo (así la app puede reintentar sin duplicar).
    """
    if uuid_cliente:
        previo = Movimiento.objects.filter(uuid_cliente=uuid_cliente).first()
        if previo:
            return previo

    if motivo not in MOTIVOS_POR_TIPO.get(tipo, set()):
        raise ErrorInventario(f'El motivo "{motivo}" no corresponde a un movimiento de tipo "{tipo}".')
    if tipo in (T.ENTRADA, T.SALIDA) and cantidad <= 0:
        raise ErrorInventario("La cantidad debe ser mayor que cero.")
    if tipo == T.AJUSTE and cantidad == 0:
        raise ErrorInventario("Un ajuste no puede ser de cero piezas.")
    if not variante.activo:
        raise ErrorInventario("Esta variante está desactivada.")

    delta = -cantidad if tipo == T.SALIDA else cantidad

    existencia, _ = Existencia.objects.select_for_update().get_or_create(
        variante=variante, ubicacion=ubicacion, defaults={"cantidad": 0}
    )
    nueva = existencia.cantidad + delta
    if nueva < 0:
        raise ErrorInventario(
            f"Solo hay {existencia.cantidad} pza(s) de {variante} en {ubicacion}."
        )
    existencia.cantidad = nueva
    existencia.save(update_fields=["cantidad"])

    return Movimiento.objects.create(
        variante=variante,
        ubicacion=ubicacion,
        tipo=tipo,
        motivo=motivo,
        cantidad=cantidad,
        usuario=usuario,
        nota=nota,
        uuid_cliente=uuid_cliente,
    )


@transaction.atomic
def alta_rapida(*, usuario, categoria, modelo_telefono, nombre_producto, color="", material="",
                codigo_barras="", precio=Decimal("0"), costo=Decimal("0"), cantidad=0, ubicacion=None):
    """Da de alta una variante nueva desde la app y registra su entrada inicial."""
    codigo_barras = (codigo_barras or "").strip()
    if codigo_barras and Variante.objects.filter(codigo_barras__iexact=codigo_barras).exists():
        raise ErrorInventario("Ese código ya está registrado; búscalo y registra una entrada.")
    if cantidad > 0 and ubicacion is None:
        raise ErrorInventario("Elige en qué ubicación se guardan las piezas.")

    producto, _ = Producto.objects.get_or_create(
        categoria=categoria,
        modelo_telefono=modelo_telefono,
        nombre=nombre_producto.strip(),
    )
    variante = Variante.objects.create(
        producto=producto,
        color=color.strip(),
        material=material.strip(),
        codigo_barras=codigo_barras or generar_codigo_variante(),
        precio=precio,
        costo=costo,
        creado_por=usuario,
    )
    if cantidad > 0:
        registrar_movimiento(
            variante=variante,
            ubicacion=ubicacion,
            tipo=T.ENTRADA,
            motivo=M.ALTA,
            cantidad=cantidad,
            usuario=usuario,
        )
    return variante
