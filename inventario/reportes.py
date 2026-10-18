"""Reporte de inventario en PDF, agrupado por categoría.

Este módulo NO depende de Django: recibe datos simples (listas de dicts) y devuelve
los bytes del PDF. Así se puede probar y reutilizar sin base de datos.

Cada fila de `filas` es un dict con:
    categoria, marca, modelo, producto, color, material, codigo,
    precio (Decimal), costo (Decimal), stock_minimo (int),
    ubicaciones: lista de (nombre_ubicacion, cantidad)
"""
from collections import OrderedDict
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ACENTO = colors.HexColor("#B45309")
TINTE = colors.HexColor("#FBF3EA")
LINEA = colors.HexColor("#E3DDD4")
SUAVE = colors.HexColor("#6B6359")
ALERTA = colors.HexColor("#B91C1C")
AVISO = colors.HexColor("#A16207")

estilo = ParagraphStyle("base", fontName="Helvetica", fontSize=8, leading=10)
estilo_suave = ParagraphStyle("suave", parent=estilo, textColor=SUAVE, fontSize=7, leading=9)
estilo_der = ParagraphStyle("der", parent=estilo, alignment=TA_RIGHT)
estilo_cab = ParagraphStyle("cab", parent=estilo, fontName="Helvetica-Bold", textColor=colors.white)
estilo_cab_der = ParagraphStyle("cabder", parent=estilo_cab, alignment=TA_RIGHT)
estilo_titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=15, leading=19)
estilo_sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=12, textColor=SUAVE)
estilo_seccion = ParagraphStyle("seccion", fontName="Helvetica-Bold", fontSize=11, leading=14,
                                textColor=ACENTO, spaceAfter=4)


def dinero(valor):
    return f"${Decimal(valor):,.2f}"


def entero(valor):
    return f"{int(valor):,}"


def p(texto, st=estilo):
    return Paragraph(escape(str(texto)), st)


def estado(stock, minimo):
    """Etiqueta de alerta para la fila: Agotado, Bajo o vacío."""
    if stock <= 0:
        return "Agotado"
    if minimo and stock < minimo:
        return "Bajo"
    return ""


def resumir(filas):
    """Totales por categoría, en el orden en que aparecen. Devuelve OrderedDict."""
    resumen = OrderedDict()
    for f in filas:
        r = resumen.setdefault(f["categoria"], {
            "variantes": 0, "agotadas": 0, "bajas": 0, "piezas": 0,
            "valor_costo": Decimal("0"), "valor_venta": Decimal("0"),
        })
        stock = sum(c for _, c in f["ubicaciones"])
        r["variantes"] += 1
        r["piezas"] += stock
        r["valor_costo"] += Decimal(f["costo"]) * stock
        r["valor_venta"] += Decimal(f["precio"]) * stock
        e = estado(stock, f["stock_minimo"])
        r["agotadas"] += e == "Agotado"
        r["bajas"] += e == "Bajo"
    return resumen


class _CanvasNumerado(rl_canvas.Canvas):
    """Canvas que escribe "Página X de Y" (necesita conocer el total al final)."""

    def __init__(self, *args, pie="", **kwargs):
        super().__init__(*args, **kwargs)
        self._paginas = []
        self._pie = pie

    def showPage(self):
        self._paginas.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._paginas)
        for estado_pag in self._paginas:
            self.__dict__.update(estado_pag)
            self.setFont("Helvetica", 7)
            self.setFillColor(SUAVE)
            ancho, _ = letter
            self.drawString(1.5 * cm, 1 * cm, self._pie)
            self.drawRightString(ancho - 1.5 * cm, 1 * cm, f"Página {self._pageNumber} de {total}")
            super().showPage()
        super().save()


def _tabla_resumen(resumen, mostrar_costos):
    cab = ["Categoría", "Variantes", "Agotadas", "Bajo mínimo", "Piezas"]
    if mostrar_costos:
        cab += ["Valor a costo", "Valor a venta"]
    datos = [[p(c, estilo_cab if i == 0 else estilo_cab_der) for i, c in enumerate(cab)]]
    tot = {"variantes": 0, "agotadas": 0, "bajas": 0, "piezas": 0,
           "valor_costo": Decimal("0"), "valor_venta": Decimal("0")}
    for cat, r in resumen.items():
        fila = [p(cat), p(entero(r["variantes"]), estilo_der), p(entero(r["agotadas"]), estilo_der),
                p(entero(r["bajas"]), estilo_der), p(entero(r["piezas"]), estilo_der)]
        if mostrar_costos:
            fila += [p(dinero(r["valor_costo"]), estilo_der), p(dinero(r["valor_venta"]), estilo_der)]
        datos.append(fila)
        for k in tot:
            tot[k] += r[k]
    negrita = ParagraphStyle("tot", parent=estilo_der, fontName="Helvetica-Bold")
    fila_tot = [p("Total", ParagraphStyle("totl", parent=estilo, fontName="Helvetica-Bold")),
                p(entero(tot["variantes"]), negrita), p(entero(tot["agotadas"]), negrita),
                p(entero(tot["bajas"]), negrita), p(entero(tot["piezas"]), negrita)]
    if mostrar_costos:
        fila_tot += [p(dinero(tot["valor_costo"]), negrita), p(dinero(tot["valor_venta"]), negrita)]
    datos.append(fila_tot)

    anchos = [5.2 * cm, 2 * cm, 2 * cm, 2.2 * cm, 2 * cm]
    if mostrar_costos:
        anchos += [2.6 * cm, 2.6 * cm]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACENTO),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, LINEA),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t, tot


def _tabla_categoria(filas, mostrar_costos):
    cab = ["Producto", "Código", "Ubicación (piezas)", "Stock", "Mín.", "Precio"]
    if mostrar_costos:
        cab.append("Valor a costo")
    datos = [[p(c, estilo_cab if i < 3 else estilo_cab_der) for i, c in enumerate(cab)]]
    estilos = []
    for i, f in enumerate(filas, start=1):
        stock = sum(c for _, c in f["ubicaciones"])
        detalle = " · ".join(x for x in [f["color"], f["material"]] if x)
        nombre = f"<b>{escape(f['marca'])} {escape(f['modelo'])}</b> · {escape(f['producto'])}"
        if detalle:
            nombre += f"<br/><font color='#6B6359'>{escape(detalle)}</font>"
        ubic = "<br/>".join(f"{escape(n)} ({c})" for n, c in f["ubicaciones"] if c > 0) or "—"
        e = estado(stock, f["stock_minimo"])
        stock_txt = f"<b>{entero(stock)}</b>" + (f"<br/><font size='6.5'>{e}</font>" if e else "")
        fila = [
            Paragraph(nombre, estilo),
            p(f["codigo"], estilo_suave),
            Paragraph(ubic, estilo),
            Paragraph(stock_txt, estilo_der),
            p(f["stock_minimo"] or "—", estilo_der),
            p(dinero(f["precio"]), estilo_der),
        ]
        if mostrar_costos:
            fila.append(p(dinero(Decimal(f["costo"]) * stock), estilo_der))
        datos.append(fila)
        if e == "Agotado":
            estilos.append(("TEXTCOLOR", (3, i), (3, i), ALERTA))
            estilos.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FDF2F2")))
        elif e == "Bajo":
            estilos.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF9EC")))

    if mostrar_costos:
        anchos = [5.1 * cm, 2.6 * cm, 4.4 * cm, 1.3 * cm, 1 * cm, 1.7 * cm, 2.1 * cm]
    else:
        anchos = [6.1 * cm, 2.6 * cm, 5.2 * cm, 1.5 * cm, 1.2 * cm, 1.6 * cm]
    t = Table(datos, colWidths=anchos, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACENTO),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        *estilos,
    ]))
    return t


def generar_reporte_inventario(filas, *, generado_por, fecha_texto, mostrar_costos):
    """Devuelve los bytes del PDF. `filas` debe venir ordenada por categoría."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.6 * cm,
        title="Reporte de inventario", author="Los Churros Rellenos",
    )
    resumen = resumir(filas)
    historia = [
        Paragraph("Reporte de inventario por categoría", estilo_titulo),
        Paragraph(f"Los Churros Rellenos · {escape(fecha_texto)} · generado por {escape(generado_por)}", estilo_sub),
        Spacer(1, 0.5 * cm),
    ]
    if not filas:
        historia.append(Paragraph("No hay productos registrados.", estilo))
    else:
        tabla_res, tot = _tabla_resumen(resumen, mostrar_costos)
        frase = (f"{entero(tot['piezas'])} piezas en {entero(tot['variantes'])} variantes. "
                 f"{entero(tot['agotadas'])} agotadas y {entero(tot['bajas'])} por debajo del mínimo.")
        if mostrar_costos:
            frase += f" Capital en inventario: {dinero(tot['valor_costo'])} a costo."
        historia += [Paragraph(escape(frase), estilo), Spacer(1, 0.3 * cm), tabla_res]

        for cat in resumen:
            filas_cat = [f for f in filas if f["categoria"] == cat]
            r = resumen[cat]
            titulo = Paragraph(
                f"{escape(cat)} <font size='8' color='#6B6359'>· {entero(r['piezas'])} piezas en "
                f"{entero(r['variantes'])} variantes</font>", estilo_seccion)
            tabla = _tabla_categoria(filas_cat, mostrar_costos)
            historia += [Spacer(1, 0.6 * cm), CondPageBreak(4 * cm), titulo, tabla]

    pie = "Agotado = sin piezas · Bajo = por debajo del stock mínimo"
    doc.build(historia, canvasmaker=lambda *a, **k: _CanvasNumerado(*a, pie=pie, **k))
    return buffer.getvalue()
