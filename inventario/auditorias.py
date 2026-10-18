"""Auditoría de inventario: contar físicamente una zona y ajustar el sistema a lo contado.

Flujo:
1. iniciar_auditoria(zona)      -> estado "abierta". Cualquier usuario cuenta desde la app.
2. registrar_conteo(...)        -> suma o fija las piezas de un producto en una caja.
3. terminar_conteo(...)         -> estado "revision". Lo no contado se toma como 0.
4. aplicar_auditoria(...)       -> solo administradores. Crea ajustes (motivo "conteo")
                                   para que el sistema quede igual a lo contado.
   reabrir_auditoria / cancelar_auditoria para corregir el rumbo.

El conteo es "a ciegas": quien cuenta no ve cuántas piezas dice el sistema, para no sesgarlo.
"""
from django.db import transaction
from django.utils import timezone

from catalogo.models import Variante

from .models import Auditoria, ConteoAuditoria, Existencia, Movimiento, Ubicacion
from .services import ErrorInventario, registrar_movimiento

E = Auditoria.Estado
EN_CURSO = (E.ABIERTA, E.REVISION)


def zonas_disponibles():
    return sorted(set(Ubicacion.objects.filter(activo=True).values_list("zona", flat=True)), key=str.lower)


def iniciar_auditoria(*, zona, usuario):
    """Crea la auditoría de una zona, o devuelve la que ya está en curso para esa zona."""
    zona = (zona or "").strip()
    if zona not in zonas_disponibles():
        raise ErrorInventario("Esa zona no existe.")
    en_curso = Auditoria.objects.filter(zona=zona, estado__in=EN_CURSO).first()
    if en_curso:
        return en_curso
    return Auditoria.objects.create(zona=zona, creada_por=usuario)


def _exigir_estado(auditoria, *estados):
    if auditoria.estado not in estados:
        raise ErrorInventario(f"La auditoría está {auditoria.get_estado_display().lower()}; no se puede hacer eso.")


def registrar_conteo(*, auditoria, variante, ubicacion, usuario, sumar=None, fijar=None):
    """Suma piezas (al escanear) o fija la cantidad (al teclearla). Devuelve el ConteoAuditoria."""
    _exigir_estado(auditoria, E.ABIERTA)
    if ubicacion.zona != auditoria.zona:
        raise ErrorInventario(f"{ubicacion} no pertenece a {auditoria.zona}.")
    if (sumar is None) == (fijar is None):
        raise ErrorInventario("Indica cuántas piezas sumar o fijar.")
    with transaction.atomic():
        conteo, _ = ConteoAuditoria.objects.select_for_update().get_or_create(
            auditoria=auditoria, variante=variante, ubicacion=ubicacion,
            defaults={"actualizado_por": usuario},
        )
        nuevo = conteo.contado + sumar if sumar is not None else fijar
        if nuevo < 0:
            raise ErrorInventario("El conteo no puede ser negativo.")
        conteo.contado = nuevo
        conteo.actualizado_por = usuario
        conteo.save()
    return conteo


def lineas_auditoria(auditoria):
    """Todo lo que hay que revisar en la zona: lo que el sistema espera + lo que se contó.

    Cada línea: variante, ubicacion, sistema (stock actual), contado, contada (si alguien la contó),
    diferencia (contado - sistema). Ordenadas por ubicación y producto.
    """
    existencias = {
        (e.variante_id, e.ubicacion_id): e
        for e in Existencia.objects.filter(ubicacion__zona=auditoria.zona).select_related(
            "variante__producto__modelo_telefono__marca", "ubicacion"
        )
    }
    conteos = {
        (c.variante_id, c.ubicacion_id): c
        for c in auditoria.conteos.select_related("variante__producto__modelo_telefono__marca", "ubicacion")
    }
    claves = {k for k, e in existencias.items() if e.cantidad > 0 and e.ubicacion.activo} | set(conteos)
    lineas = []
    for clave in claves:
        e, c = existencias.get(clave), conteos.get(clave)
        origen = c or e
        sistema = e.cantidad if e else 0
        contado = c.contado if c else 0
        lineas.append({
            "variante": origen.variante,
            "ubicacion": origen.ubicacion,
            "sistema": sistema,
            "contado": contado,
            "contada": c is not None,
            "diferencia": contado - sistema,
        })
    lineas.sort(key=lambda l: (str(l["ubicacion"]).lower(), str(l["variante"]).lower()))
    return lineas


def resumen(lineas):
    return {
        "lineas": len(lineas),
        "contadas": sum(l["contada"] for l in lineas),
        "con_diferencia": sum(l["diferencia"] != 0 for l in lineas),
        "faltantes": sum(-l["diferencia"] for l in lineas if l["diferencia"] < 0),
        "sobrantes": sum(l["diferencia"] for l in lineas if l["diferencia"] > 0),
    }


def terminar_conteo(*, auditoria, usuario):
    _exigir_estado(auditoria, E.ABIERTA)
    auditoria.estado = E.REVISION
    auditoria.terminada = timezone.now()
    auditoria.save(update_fields=["estado", "terminada"])
    return auditoria


def reabrir_auditoria(*, auditoria, usuario):
    _exigir_estado(auditoria, E.REVISION)
    auditoria.estado = E.ABIERTA
    auditoria.terminada = None
    auditoria.save(update_fields=["estado", "terminada"])
    return auditoria


def cancelar_auditoria(*, auditoria, usuario):
    _exigir_estado(auditoria, *EN_CURSO)
    auditoria.estado = E.CANCELADA
    auditoria.save(update_fields=["estado"])
    return auditoria


@transaction.atomic
def aplicar_auditoria(*, auditoria, usuario):
    """Ajusta el stock de la zona para que sea igual a lo contado y guarda el resultado."""
    auditoria = Auditoria.objects.select_for_update().get(pk=auditoria.pk)
    _exigir_estado(auditoria, E.REVISION)
    # Bloquea el stock de la zona mientras se calcula y ajusta
    list(Existencia.objects.select_for_update().filter(ubicacion__zona=auditoria.zona))
    lineas = lineas_auditoria(auditoria)
    for l in lineas:
        if l["diferencia"]:
            registrar_movimiento(
                variante=l["variante"], ubicacion=l["ubicacion"],
                tipo=Movimiento.Tipo.AJUSTE, motivo=Movimiento.Motivo.CONTEO,
                cantidad=l["diferencia"], usuario=usuario,
                nota=f"Auditoría #{auditoria.pk} ({auditoria.zona})",
            )
    r = resumen(lineas)
    auditoria.estado = E.APLICADA
    auditoria.aplicada = timezone.now()
    auditoria.aplicada_por = usuario
    auditoria.lineas = r["lineas"]
    auditoria.lineas_con_diferencia = r["con_diferencia"]
    auditoria.piezas_faltantes = r["faltantes"]
    auditoria.piezas_sobrantes = r["sobrantes"]
    auditoria.save()
    return auditoria, r


def variante_por_id(pk):
    return Variante.objects.filter(pk=pk, activo=True).first()
