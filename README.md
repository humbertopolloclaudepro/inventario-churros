# Inventario · Los Churros Rellenos

App para saber **dónde está cada accesorio** en la tienda y **qué mercancía se está quedando sin vender**.

- **App del celular** (`/app/`): buscar o escanear un producto y ver su ubicación ("Cajonera 2 · Nivel B"),
  registrar entradas y salidas, y dar de alta productos nuevos.
- **Panel del dueño** (`/admin/`): catálogo, ubicaciones, historial de movimientos, radar de
  obsolescencia (sin venta en 30/60/90 días), stock bajo y etiquetas QR en PDF.

Hecho con Django + Django REST Framework y una app web instalable (PWA).

## Arrancar en tu computadora

Necesitas Python 3.11 o más reciente.

```bash
git clone <url-del-repo>
cd inventario-churros
python -m venv .venv
source .venv/bin/activate          # En Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Solo la primera vez: genera las migraciones y súbelas al repo
python manage.py makemigrations catalogo inventario

python manage.py migrate
python manage.py crear_roles
python manage.py createsuperuser
python manage.py test               # deben pasar todas
python manage.py runserver
```

Abre http://127.0.0.1:8000/admin/ (panel) y http://127.0.0.1:8000/app/ (app).

### Datos de prueba

```bash
python manage.py importar_catalogo docs/plantilla_catalogo.csv --usuario <tu-usuario>
```

Para la tienda real: en Excel, acomoda las columnas como en `docs/plantilla_catalogo.csv` y usa
*Archivo > Guardar como > CSV UTF-8*. Prueba primero con `--prueba` para validar sin guardar.

### Usuarios

1. En `/admin/` > Usuarios, crea a cada persona.
2. Asígnale el grupo **Vendedor** o **Administrador**.
3. A los administradores márcales también **Es staff** para que entren al panel.

## Probar la app en un celular

La cámara del navegador **solo funciona con HTTPS** (o en `localhost`). Opciones:

- Desplegar en un servicio con HTTPS (ver abajo), o
- Exponer tu `runserver` con un túnel HTTPS (por ejemplo ngrok o Cloudflare Tunnel) y agregar ese
  dominio a `DJANGO_ALLOWED_HOSTS` y `DJANGO_CSRF_TRUSTED_ORIGINS`.

En el celular, abre la dirección en Chrome, inicia sesión y elige *Agregar a pantalla de inicio*.

## Desplegar

Cualquier servicio con Python, PostgreSQL y HTTPS sirve. Variables necesarias en `.env.example`.

```bash
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn config.wsgi
```

## Trabajo en equipo

- Lee `CLAUDE.md`: resume la arquitectura y las reglas del proyecto (también lo usa Claude Code).
- Cada tarea en su rama y entra a `main` por pull request revisado por la otra persona.
- GitHub Actions corre las pruebas en cada PR.
