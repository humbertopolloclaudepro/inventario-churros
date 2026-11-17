import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from inventario.permisos import GRUPO_ADMIN


class Command(BaseCommand):
    help = (
        "Crea el usuario dueño (administrador) con DJANGO_SUPERUSER_USERNAME y "
        "DJANGO_SUPERUSER_PASSWORD, o le pone esa contraseña si ya existe. "
        "Sirve para recuperar el acceso en servicios sin consola (Render gratis)."
    )

    def handle(self, *args, **options):
        usuario = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        contrasena = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not usuario or not contrasena:
            self.stdout.write(self.style.WARNING(
                "Sin DJANGO_SUPERUSER_USERNAME o DJANGO_SUPERUSER_PASSWORD: no se crea el usuario dueño."
            ))
            return

        modelo = get_user_model()
        dueno, creado = modelo.objects.get_or_create(username=usuario)
        dueno.set_password(contrasena)
        dueno.is_staff = True
        dueno.is_superuser = True
        dueno.is_active = True
        dueno.save()
        grupo, _ = Group.objects.get_or_create(name=GRUPO_ADMIN)
        dueno.groups.add(grupo)
        accion = "creado" if creado else "actualizado (contraseña de DJANGO_SUPERUSER_PASSWORD)"
        self.stdout.write(self.style.SUCCESS(f'Usuario dueño "{usuario}" {accion}.'))
