# Los Churros Rellenos · Control de inventario

Proyecto escolar (UNAM, Dirección de Proyectos, 2027-1). Sistema de micro-logística para una
tienda de accesorios de celular: saber **dónde** está cada pieza y detectar mercancía que se
está volviendo obsoleta (deadstock).

Equipo: **2 personas**. Calendario: desarrollo 19–30 oct 2026, prueba en tienda 2–6 nov,
iteración 9–13 nov, prueba final 17–20 nov.

## Qué es y qué NO es

- ES control de inventario: ubicaciones físicas, entradas, salidas, trazabilidad, radar de obsolescencia.
- NO es punto de venta. La tienda cobra en efectivo fuera del sistema. No hay montos, tickets,
  cortes de caja ni métodos de pago. Una venta es solo una **salida con motivo "venta"**.
- No agregues funciones de ventas (totales en dinero, cobro) aunque parezcan fáciles.

## Arquitectura

- `config/` — settings y URLs. SQLite en local; PostgreSQL en producción vía `DATABASE_URL`.
- `catalogo/` — Categoria > Marca > ModeloTelefono > Producto > Variante (el SKU).
  El admin de esta app es el **dashboard del dueño** (radar, stock bajo, etiquetas).
- `inventario/` — Ubicacion, Existencia (stock por variante y ubicación), Movimiento (inmutable),
  reglas de negocio (`services.py`), API para la app (`api.py`, `api_urls.py`), etiquetas QR (`etiquetas.py`),
  reporte PDF por categoría (`reportes.py` sin Django + `views.py`, en `/reportes/inventario.pdf`),
  importación desde Excel/CSV (`importacion.py`: leer y validar sin Django, `importar_filas` guarda;
  la usan la página `/admin/importar/` y el comando `importar_catalogo`),
  auditoría de inventario (`auditorias.py`: modelos Auditoria/ConteoAuditoria; se cuenta a ciegas desde la app,
  pestaña Auditar, y un administrador aplica los ajustes con motivo "conteo").
- `pwa/` — la app del celular: una sola página (`templates/pwa/app.html` + `static/pwa/app.js`),
  JavaScript sin frameworks, escáner con html5-qrcode, instalable en Android.

No hay un dashboard propio: el panel de administración de Django ES el dashboard.

## Reglas que no se rompen

1. **El stock solo cambia con `inventario.services.registrar_movimiento`.** Nunca edites
   `Existencia.cantidad` directamente ni crees `Movimiento` a mano.
2. **Los movimientos son inmutables.** Un error se corrige con un movimiento de ajuste (solo admin).
3. **Motivos por tipo** (ver `MOTIVOS_POR_TIPO`): entrada = compra, devolución de cliente, alta;
   salida = venta, merma, devolución a proveedor; ajuste = conteo, corrección.
4. **Roles:** Administrador (ve costos, hace ajustes, entra a /admin/) y Vendedor (busca, registra
   entradas y salidas, da de alta productos). La API **oculta `costo`** a vendedores e ignora el
   costo que envíen.
5. La app manda `uuid_cliente` en cada movimiento; el servidor no duplica si se reenvía.
6. Mensajes de error para el usuario en español, claros y accionables ("Solo hay 2 pzs en Cajonera 2").

## Convenciones

- Código, modelos y variables en español, sin acentos en identificadores.
- Cada cambio de lógica lleva prueba en `inventario/tests.py` (o en un `tests.py` de su app).
- Migraciones: si cambias un modelo, corre `makemigrations` y súbelas en el mismo PR.
- PRs pequeños; la otra persona revisa antes de integrar a `main`.

## Comandos

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations catalogo inventario   # solo la primera vez, luego súbelas
python manage.py migrate
python manage.py crear_roles
python manage.py createsuperuser
python manage.py runserver
python manage.py test
python manage.py importar_catalogo archivo.xlsx --usuario admin --prueba  # revisar sin guardar
```

## Alcance

- P0 (piloto): catálogo + importación CSV, ubicaciones con QR, buscador espacial, escaneo,
  entradas/salidas, alta rápida desde la app (vendedores incluidos), roles, trazabilidad,
  radar de obsolescencia 30/60/90 días, etiquetas QR en PDF.
- Hecho después del MVP: reporte PDF por categoría, importación desde Excel en el panel, cambio de contraseña,
  botón Panel en la app, auditoría por zona.
- P1 (iteración): cola offline de movimientos en IndexedDB (ver TODO en `pwa/templates/pwa/sw.js`),
  alerta de stock bajo (ya existe como filtro en el admin; falta avisar en la app).
- Fuera: rol almacenista, dashboard propio con gráficas,
  sugerencias de reabastecimiento, sincronización en tiempo real, integración con punto de venta.
