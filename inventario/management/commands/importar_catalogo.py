"""Importa el inventario inicial desde un CSV (en Excel: Archivo > Guardar como > CSV UTF-8).

Columnas (ver docs/plantilla_catalogo.csv):
    categoria, marca, modelo, producto, color, material, codigo_barras,
    precio, costo, stock_minimo, zona, nivel, caja, cantidad

Uso:
    python manage.py importar_catalogo inventario.csv --usuario admin
    python manage.py importar_catalogo inventario.csv --usuario admin --prueba
"""
import csv
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogo.models import Categoria, Marca, ModeloTelefono, Producto, Variante
from inventario.models import Movimiento, Ubicacion
from inventario.services import registrar_movimiento

OBLIGATORIAS = ["categoria", "marca", "modelo", "producto"]


class Prueba(Exception):
    """Se lanza para deshacer todo en modo --prueba."""


def _decimal(valor, fila, campo):
    valor = (valor or "0").replace("$", "").replace(",", "").strip() or "0"
    try:
        return Decimal(valor)
    except InvalidOperation as e:
        raise CommandError(f"Fila {fila}: '{campo}' no es un número ({valor}).") from e


def _entero(valor, fila, campo):
    valor = (valor or "0").strip() or "0"
    try:
        return int(Decimal(valor))
    except InvalidOperation as e:
        raise CommandError(f"Fila {fila}: '{campo}' no es un número entero ({valor}).") from e


class Command(BaseCommand):
    help = "Importa categorías, modelos, variantes, ubicaciones y stock inicial desde un CSV."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--usuario", required=True, help="Usuario al que se atribuyen las entradas.")
        parser.add_argument("--prueba", action="store_true", help="Valida el archivo sin guardar nada.")

    def handle(self, *args, archivo, usuario, prueba, **options):
        try:
            user = get_user_model().objects.get(username=usuario)
        except get_user_model().DoesNotExist as e:
            raise CommandError(f"No existe el usuario '{usuario}'.") from e

        with open(archivo, newline="", encoding="utf-8-sig") as f:
            muestra = f.read(2048)
            f.seek(0)
            try:
                dialecto = csv.Sniffer().sniff(muestra, delimiters=",;")
            except csv.Error:
                dialecto = csv.excel  # Coma como separador
            filas = list(csv.DictReader(f, dialect=dialecto))

        if not filas:
            raise CommandError("El archivo está vacío.")
        faltan = [c for c in OBLIGATORIAS if c not in filas[0]]
        if faltan:
            raise CommandError(f"Faltan columnas: {', '.join(faltan)}")

        resumen = {"variantes nuevas": 0, "variantes existentes": 0, "ubicaciones nuevas": 0, "piezas": 0}
        try:
            with transaction.atomic():
                for n, fila in enumerate(filas, start=2):
                    self._importar_fila(n, {k.strip(): (v or "").strip() for k, v in fila.items() if k}, user, resumen)
                if prueba:
                    raise Prueba
        except Prueba:
            self.stdout.write(self.style.WARNING("Modo prueba: no se guardó nada."))

        for clave, valor in resumen.items():
            self.stdout.write(f"  {clave}: {valor}")
        if not prueba:
            self.stdout.write(self.style.SUCCESS("Importación terminada."))

    def _importar_fila(self, n, fila, user, resumen):
        for campo in OBLIGATORIAS:
            if not fila.get(campo):
                raise CommandError(f"Fila {n}: falta '{campo}'.")

        categoria, _ = Categoria.objects.get_or_create(nombre=fila["categoria"])
        marca, _ = Marca.objects.get_or_create(nombre=fila["marca"])
        modelo, _ = ModeloTelefono.objects.get_or_create(marca=marca, nombre=fila["modelo"])
        producto, _ = Producto.objects.get_or_create(
            categoria=categoria, modelo_telefono=modelo, nombre=fila["producto"]
        )

        codigo = fila.get("codigo_barras", "")
        datos = {
            "precio": _decimal(fila.get("precio"), n, "precio"),
            "costo": _decimal(fila.get("costo"), n, "costo"),
            "stock_minimo": _entero(fila.get("stock_minimo"), n, "stock_minimo"),
            "creado_por": user,
        }
        if codigo:
            variante, creada = Variante.objects.get_or_create(
                codigo_barras=codigo,
                defaults={"producto": producto, "color": fila.get("color", ""),
                          "material": fila.get("material", ""), **datos},
            )
        else:
            variante, creada = Variante.objects.get_or_create(
                producto=producto, color=fila.get("color", ""), material=fila.get("material", ""),
                defaults=datos,
            )
        resumen["variantes nuevas" if creada else "variantes existentes"] += 1

        cantidad = _entero(fila.get("cantidad"), n, "cantidad")
        if cantidad <= 0:
            return
        if not fila.get("zona"):
            raise CommandError(f"Fila {n}: tiene cantidad pero no 'zona'.")
        if not creada:
            self.stdout.write(self.style.WARNING(
                f"Fila {n}: {variante} ya existía; no se suma stock para no duplicarlo."
            ))
            return

        ubicacion, ub_nueva = Ubicacion.objects.get_or_create(
            zona=fila["zona"], nivel=fila.get("nivel", ""), caja=fila.get("caja", "")
        )
        resumen["ubicaciones nuevas"] += int(ub_nueva)
        registrar_movimiento(
            variante=variante, ubicacion=ubicacion, tipo=Movimiento.Tipo.ENTRADA,
            motivo=Movimiento.Motivo.ALTA, cantidad=cantidad, usuario=user, nota="Importación inicial",
        )
        resumen["piezas"] += cantidad
