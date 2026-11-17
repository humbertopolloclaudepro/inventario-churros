# EasyStock · Los Churros Rellenos

App para saber **dónde está cada accesorio** en la tienda y **qué mercancía se está quedando sin vender**.

- **App del celular** (`/app/`, también como **APK de Android**): lista del inventario, buscar o escanear
  un producto y ver su ubicación ("Cajonera 2 · Nivel B"), registrar entradas y salidas, y dar de alta
  productos nuevos con fotografía de referencia (cámara o galería).
- **Panel del dueño** (`/admin/`): catálogo, ubicaciones, historial de movimientos, radar de
  obsolescencia (sin venta en 30/60/90 días), stock bajo, etiquetas QR, reporte PDF,
  importación desde Excel e historial de auditorías.
- **Auditoría** (pestaña *Auditar* de la app): se cuenta una zona escaneando cada caja y sus piezas;
  un administrador revisa las diferencias y ajusta el inventario.

Hecho con Django + Django REST Framework y una app web instalable (PWA) con el formato visual de
EasyStock, empaquetada como APK con Capacitor (carpeta `android-app/`).

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

Para la tienda real, lo más fácil es el panel: **Herramientas > Importar inventario desde Excel**.
Ahí se descarga la plantilla, se sube el `.xlsx` y se revisan los errores antes de guardar.
Desde la consola también funciona con `.xlsx` o `.csv`; usa `--prueba` para revisar sin guardar.

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

### Render (recomendado, gratis para el piloto)

1. Entra a [render.com](https://render.com) con tu cuenta de GitHub.
2. **New > Blueprint** y elige este repositorio. Render lee `render.yaml` y crea el servidor y la base de datos.
3. Te pide tres valores:
   - `DJANGO_SUPERUSER_USERNAME` y `DJANGO_SUPERUSER_PASSWORD`: el usuario del dueño (administrador).
   - `CODIGO_REGISTRO`: el código que deben escribir los empleados en "Crear nueva cuenta"
     (déjalo vacío si prefieres crear tú cada usuario desde el panel).
4. Al terminar, la dirección queda como `https://easystock-xxxx.onrender.com`. Úsala para el APK
   (ver `android-app/LEEME.md`).

En el plan gratis el servidor se "duerme" tras 15 minutos sin uso y tarda ~1 minuto en despertar,
y la base de datos gratis caduca a los 30 días. Para la operación real conviene el plan de pago más bajo.

### Otro servicio

Cualquier servicio con Python, PostgreSQL y HTTPS sirve. Variables necesarias en `.env.example`.

```bash
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn config.wsgi
```

## APK de Android

El APK abre el servidor dentro de una app nativa con el logo de EasyStock y permiso de cámara.
Se compila en GitHub Actions (**Actions > APK Android > Run workflow**) y queda en **Releases**.
Instrucciones completas en [`android-app/LEEME.md`](android-app/LEEME.md).

## Trabajo en equipo

- Lee `CLAUDE.md`: resume la arquitectura y las reglas del proyecto (también lo usa Claude Code).
- Cada tarea en su rama y entra a `main` por pull request revisado por la otra persona.
- GitHub Actions corre las pruebas en cada PR.
