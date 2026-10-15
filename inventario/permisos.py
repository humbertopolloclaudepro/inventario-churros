"""Roles del sistema. Los grupos se crean con: python manage.py crear_roles"""

GRUPO_ADMIN = "Administrador"
GRUPO_VENDEDOR = "Vendedor"


def es_admin(user):
    """Administrador: ve costos y puede hacer ajustes de inventario."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=GRUPO_ADMIN).exists()
