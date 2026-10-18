from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from catalogo.admin import anotar_variantes
from catalogo.models import Categoria, Marca, ModeloTelefono, Producto, Variante
from inventario.models import Existencia, Movimiento, Ubicacion
from inventario.permisos import GRUPO_ADMIN, GRUPO_VENDEDOR
from inventario.services import ErrorInventario, alta_rapida, registrar_movimiento

T, M = Movimiento.Tipo, Movimiento.Motivo
BASE = Path(__file__).resolve().parent.parent


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("crear_roles", stdout=StringIO())
        User = get_user_model()
        cls.admin = User.objects.create_user("dueno", password="x")
        cls.admin.groups.add(Group.objects.get(name=GRUPO_ADMIN))
        cls.vendedor = User.objects.create_user("vendedor", password="x")
        cls.vendedor.groups.add(Group.objects.get(name=GRUPO_VENDEDOR))

        cls.fundas = Categoria.objects.create(nombre="Fundas")
        apple = Marca.objects.create(nombre="Apple")
        cls.iphone14 = ModeloTelefono.objects.create(marca=apple, nombre="iPhone 14")
        cls.iphone14pro = ModeloTelefono.objects.create(marca=apple, nombre="iPhone 14 Pro")
        producto = Producto.objects.create(categoria=cls.fundas, modelo_telefono=cls.iphone14, nombre="Funda uso rudo")
        cls.variante = Variante.objects.create(producto=producto, color="Negro", codigo_barras="7501", precio=250, costo=90)
        cls.cajonera = Ubicacion.objects.create(zona="Cajonera 2", nivel="B")

    def entrada(self, cantidad=5, usuario=None):
        return registrar_movimiento(
            variante=self.variante, ubicacion=self.cajonera, tipo=T.ENTRADA, motivo=M.COMPRA,
            cantidad=cantidad, usuario=usuario or self.admin,
        )

    def stock(self):
        e = Existencia.objects.filter(variante=self.variante, ubicacion=self.cajonera).first()
        return e.cantidad if e else 0


class ServiciosTests(Base):
    def test_entrada_y_salida_actualizan_stock(self):
        self.entrada(5)
        registrar_movimiento(
            variante=self.variante, ubicacion=self.cajonera, tipo=T.SALIDA, motivo=M.VENTA,
            cantidad=2, usuario=self.vendedor,
        )
        self.assertEqual(self.stock(), 3)
        self.assertEqual(Movimiento.objects.count(), 2)

    def test_no_permite_stock_negativo(self):
        self.entrada(1)
        with self.assertRaises(ErrorInventario):
            registrar_movimiento(
                variante=self.variante, ubicacion=self.cajonera, tipo=T.SALIDA, motivo=M.VENTA,
                cantidad=2, usuario=self.vendedor,
            )
        self.assertEqual(self.stock(), 1)
        self.assertEqual(Movimiento.objects.count(), 1)

    def test_motivo_debe_corresponder_al_tipo(self):
        with self.assertRaises(ErrorInventario):
            registrar_movimiento(
                variante=self.variante, ubicacion=self.cajonera, tipo=T.ENTRADA, motivo=M.VENTA,
                cantidad=1, usuario=self.admin,
            )

    def test_ajuste_negativo(self):
        self.entrada(5)
        registrar_movimiento(
            variante=self.variante, ubicacion=self.cajonera, tipo=T.AJUSTE, motivo=M.CONTEO,
            cantidad=-2, usuario=self.admin,
        )
        self.assertEqual(self.stock(), 3)

    def test_movimientos_son_inmutables(self):
        mov = self.entrada(5)
        mov.cantidad = 50
        with self.assertRaises(ValidationError):
            mov.save()
        with self.assertRaises(ValidationError):
            mov.delete()

    def test_uuid_cliente_evita_duplicados(self):
        import uuid
        clave = uuid.uuid4()
        for _ in range(2):
            registrar_movimiento(
                variante=self.variante, ubicacion=self.cajonera, tipo=T.ENTRADA, motivo=M.COMPRA,
                cantidad=3, usuario=self.admin, uuid_cliente=clave,
            )
        self.assertEqual(self.stock(), 3)
        self.assertEqual(Movimiento.objects.count(), 1)

    def test_alta_rapida_crea_variante_y_entrada(self):
        v = alta_rapida(
            usuario=self.vendedor, categoria=self.fundas, modelo_telefono=self.iphone14pro,
            nombre_producto="Funda uso rudo", color="Azul", precio=250, cantidad=4, ubicacion=self.cajonera,
        )
        self.assertEqual(v.producto.modelo_telefono, self.iphone14pro)
        self.assertTrue(v.codigo_barras.startswith("CR"))
        self.assertEqual(Existencia.objects.get(variante=v).cantidad, 4)
        self.assertEqual(Movimiento.objects.get(variante=v).motivo, M.ALTA)

    def test_alta_rapida_rechaza_codigo_repetido(self):
        with self.assertRaises(ErrorInventario):
            alta_rapida(
                usuario=self.vendedor, categoria=self.fundas, modelo_telefono=self.iphone14,
                nombre_producto="Otra", codigo_barras="7501", precio=1,
            )


class ApiTests(Base):
    def setUp(self):
        self.cliente = APIClient()

    def test_requiere_sesion(self):
        self.assertEqual(self.cliente.get("/api/buscar/?q=funda").status_code, 403)

    def test_buscar_por_palabras_muestra_ubicacion(self):
        self.entrada(3)
        self.cliente.force_authenticate(self.vendedor)
        r = self.cliente.get("/api/buscar/?q=rudo 14")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["stock_total"], 3)
        self.assertEqual(r.data[0]["existencias"][0]["ubicacion"]["nombre"], "Cajonera 2 · Nivel B")

    def test_vendedor_no_ve_costo_y_admin_si(self):
        self.cliente.force_authenticate(self.vendedor)
        self.assertNotIn("costo", self.cliente.get("/api/buscar/?q=7501").data[0])
        self.cliente.force_authenticate(self.admin)
        self.assertIn("costo", self.cliente.get("/api/buscar/?q=7501").data[0])

    def test_codigo_variante_ubicacion_y_desconocido(self):
        self.cliente.force_authenticate(self.vendedor)
        self.assertEqual(self.cliente.get("/api/codigo/?c=7501").data["tipo"], "variante")
        self.assertEqual(self.cliente.get(f"/api/codigo/?c={self.cajonera.codigo}").data["tipo"], "ubicacion")
        self.assertEqual(self.cliente.get("/api/codigo/?c=NOEXISTE").status_code, 404)

    def test_registrar_salida(self):
        self.entrada(3)
        self.cliente.force_authenticate(self.vendedor)
        r = self.cliente.post("/api/movimientos/", {
            "variante": self.variante.pk, "ubicacion": self.cajonera.pk,
            "tipo": "salida", "motivo": "venta", "cantidad": 1,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["variante"]["stock_total"], 2)

    def test_salida_sin_stock_da_error_legible(self):
        self.cliente.force_authenticate(self.vendedor)
        r = self.cliente.post("/api/movimientos/", {
            "variante": self.variante.pk, "ubicacion": self.cajonera.pk,
            "tipo": "salida", "motivo": "venta", "cantidad": 1,
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Solo hay", r.data["detail"])

    def test_vendedor_no_puede_ajustar(self):
        self.cliente.force_authenticate(self.vendedor)
        r = self.cliente.post("/api/movimientos/", {
            "variante": self.variante.pk, "ubicacion": self.cajonera.pk,
            "tipo": "ajuste", "motivo": "conteo", "cantidad": 5,
        }, format="json")
        self.assertEqual(r.status_code, 403)

    def test_vendedor_da_de_alta_sin_costo(self):
        self.cliente.force_authenticate(self.vendedor)
        r = self.cliente.post("/api/alta-rapida/", {
            "codigo_barras": "7509999", "categoria": self.fundas.pk, "modelo_telefono": self.iphone14pro.pk,
            "nombre_producto": "Funda silicón", "color": "Rojo", "precio": "180.00", "costo": "50.00",
            "cantidad": 2, "ubicacion": self.cajonera.pk,
        }, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(Variante.objects.get(codigo_barras="7509999").costo, 0)
        self.assertEqual(r.data["variante"]["stock_total"], 2)

    def test_crear_modelo_no_duplica(self):
        self.cliente.force_authenticate(self.vendedor)
        datos = {"marca": self.iphone14.marca_id, "nombre": "iphone 14"}
        r = self.cliente.post("/api/modelos/", datos, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["id"], self.iphone14.pk)
        r = self.cliente.post("/api/modelos/", {"marca": self.iphone14.marca_id, "nombre": "iPhone 15"}, format="json")
        self.assertEqual(r.status_code, 201)


class RadarTests(Base):
    def test_radar_detecta_variantes_sin_venta(self):
        self.entrada(4)
        Variante.objects.filter(pk=self.variante.pk).update(creado=timezone.now() - timedelta(days=45))
        v = anotar_variantes(Variante.objects.filter(pk=self.variante.pk)).get()
        self.assertEqual(v.stock, 4)
        self.assertIsNone(v.ultima_venta)
        self.assertEqual(v.capital, 360)
        limite = timezone.now() - timedelta(days=30)
        self.assertTrue(anotar_variantes(Variante.objects.all()).filter(stock__gt=0, ultima_actividad__lt=limite).exists())


class ImportarTests(TestCase):
    def test_importa_plantilla(self):
        get_user_model().objects.create_user("dueno", password="x")
        salida = StringIO()
        call_command("importar_catalogo", str(BASE / "docs" / "plantilla_catalogo.csv"), usuario="dueno", stdout=salida)
        self.assertEqual(Variante.objects.count(), 5)
        self.assertEqual(Ubicacion.objects.count(), 5)
        self.assertEqual(sum(Existencia.objects.values_list("cantidad", flat=True)), 35)
        # Volver a importar no duplica el stock.
        call_command("importar_catalogo", str(BASE / "docs" / "plantilla_catalogo.csv"), usuario="dueno", stdout=StringIO())
        self.assertEqual(sum(Existencia.objects.values_list("cantidad", flat=True)), 35)


class ReporteTests(Base):
    def test_requiere_sesion(self):
        r = self.client.get("/reportes/inventario.pdf")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_admin_y_vendedor_obtienen_pdf(self):
        self.entrada(4)
        for usuario in (self.admin, self.vendedor):
            self.client.force_login(usuario)
            r = self.client.get("/reportes/inventario.pdf")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r["Content-Type"], "application/pdf")
            self.assertTrue(r.content.startswith(b"%PDF"))

    def test_filas_incluyen_ubicaciones_y_agotados(self):
        from inventario.views import filas_reporte
        self.entrada(4)
        Variante.objects.create(producto=self.variante.producto, color="Rojo", codigo_barras="7502", precio=250)
        filas = filas_reporte()
        self.assertEqual(len(filas), 2)
        negra = next(f for f in filas if f["codigo"] == "7501")
        self.assertEqual(negra["ubicaciones"], [("Cajonera 2 · Nivel B", 4)])
        roja = next(f for f in filas if f["codigo"] == "7502")
        self.assertEqual(roja["ubicaciones"], [])

    def test_resumen_por_categoria(self):
        from inventario.reportes import resumir
        from inventario.views import filas_reporte
        self.entrada(4)
        r = resumir(filas_reporte())["Fundas"]
        self.assertEqual((r["variantes"], r["piezas"], r["agotadas"]), (1, 4, 0))
        self.assertEqual(r["valor_costo"], 360)

    def test_panel_muestra_enlace(self):
        jefe = get_user_model().objects.create_superuser("jefe", password="x")
        self.client.force_login(jefe)
        self.assertContains(self.client.get("/admin/"), "/reportes/inventario.pdf")
        self.assertContains(self.client.get("/admin/catalogo/variante/"), "/reportes/inventario.pdf")


class PwaTests(Base):
    def test_app_requiere_login_y_carga(self):
        self.assertEqual(self.client.get("/app/").status_code, 302)
        self.client.force_login(self.vendedor)
        r = self.client.get("/app/")
        self.assertContains(r, "Alta rápida")
        self.assertNotContains(r, 'name="costo"')
        self.assertEqual(self.client.get("/sw.js").status_code, 200)
        self.assertEqual(self.client.get("/manifest.webmanifest").status_code, 200)
