from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from inventario.permisos import GRUPO_ADMIN, GRUPO_VENDEDOR

APPS = ["catalogo", "inventario"]

# El vendedor puede consultar todo y dar de alta productos y movimientos.
# No cambia ni borra nada, y la API le oculta los costos.
PERMISOS_VENDEDOR = [
    "view_categoria", "add_categoria",
    "view_marca", "add_marca",
    "view_modelotelefono", "add_modelotelefono",
    "view_producto", "add_producto",
    "view_variante", "add_variante",
    "view_ubicacion",
    "view_existencia",
    "view_movimiento", "add_movimiento",
]


class Command(BaseCommand):
    help = "Crea (o actualiza) los grupos Administrador y Vendedor con sus permisos."

    def handle(self, *args, **options):
        admin, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
        admin.permissions.set(Permission.objects.filter(content_type__app_label__in=APPS))

        vendedor, _ = Group.objects.get_or_create(name=GRUPO_VENDEDOR)
        vendedor.permissions.set(
            Permission.objects.filter(content_type__app_label__in=APPS, codename__in=PERMISOS_VENDEDOR)
        )
        self.stdout.write(self.style.SUCCESS("Roles listos: Administrador y Vendedor."))
        self.stdout.write(
            "Recuerda: un usuario Administrador necesita además 'Es staff' para entrar al panel /admin/."
        )
