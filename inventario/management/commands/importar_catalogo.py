"""Importa el inventario desde Excel (.xlsx) o CSV, igual que la página "Importar inventario" del panel.

Columnas: ver docs/plantilla_catalogo.csv o descarga la plantilla desde el panel.

Uso:
    python manage.py importar_catalogo inventario.xlsx --usuario admin --prueba   # solo revisa
    python manage.py importar_catalogo inventario.xlsx --usuario admin            # guarda
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from inventario.importacion import ErrorArchivo, importar_filas, leer_archivo


class Command(BaseCommand):
    help = "Importa categorías, modelos, variantes, ubicaciones y stock inicial desde un .xlsx o .csv."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--usuario", required=True, help="Usuario al que se atribuyen las entradas.")
        parser.add_argument("--prueba", action="store_true", help="Revisa el archivo sin guardar nada.")

    def handle(self, *args, archivo, usuario, prueba, **options):
        User = get_user_model()
        try:
            user = User.objects.get(username=usuario)
        except User.DoesNotExist as e:
            raise CommandError(f"No existe el usuario '{usuario}'.") from e

        ruta = Path(archivo)
        if not ruta.exists():
            raise CommandError(f"No encuentro el archivo {archivo}.")
        try:
            filas = leer_archivo(ruta.name, ruta.read_bytes())
        except ErrorArchivo as e:
            raise CommandError(str(e)) from e

        r = importar_filas(filas, usuario=user, guardar=not prueba)
        for fila, mensaje in r.errores:
            self.stderr.write(f"  Fila {fila}: {mensaje}")
        if r.errores:
            raise CommandError(f"{len(r.errores)} error(es); no se guardó nada.")
        for fila, mensaje in r.avisos:
            self.stdout.write(self.style.WARNING(f"  Fila {fila}: {mensaje}"))

        self.stdout.write(f"  variantes nuevas: {r.variantes_nuevas}")
        self.stdout.write(f"  variantes existentes: {r.variantes_existentes}")
        self.stdout.write(f"  ubicaciones nuevas: {r.ubicaciones_nuevas}")
        self.stdout.write(f"  piezas: {r.piezas}")
        if prueba:
            self.stdout.write(self.style.WARNING("Modo prueba: no se guardó nada."))
        else:
            self.stdout.write(self.style.SUCCESS("Importación terminada."))
