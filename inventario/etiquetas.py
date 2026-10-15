"""Genera hojas de etiquetas QR en PDF (tamaño carta, 3 × 8 etiquetas)."""
from io import BytesIO

import qrcode
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

COLUMNAS, FILAS = 3, 8
MARGEN_X, MARGEN_Y = 0.6 * cm, 1.2 * cm


def _recortar(texto, maximo):
    return texto if len(texto) <= maximo else texto[: maximo - 1] + "…"


def generar_pdf(etiquetas):
    """etiquetas: lista de tuplas (codigo, titulo, subtitulo). Devuelve los bytes del PDF."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    ancho_pag, alto_pag = letter
    ancho = (ancho_pag - 2 * MARGEN_X) / COLUMNAS
    alto = (alto_pag - 2 * MARGEN_Y) / FILAS
    lado_qr = alto - 0.5 * cm

    for i, (codigo, titulo, subtitulo) in enumerate(etiquetas):
        pos = i % (COLUMNAS * FILAS)
        if i and pos == 0:
            pdf.showPage()
        col, fila = pos % COLUMNAS, pos // COLUMNAS
        x = MARGEN_X + col * ancho
        y = alto_pag - MARGEN_Y - (fila + 1) * alto

        imagen = qrcode.make(codigo, box_size=8, border=1).get_image()
        pdf.drawImage(ImageReader(imagen), x + 0.2 * cm, y + 0.25 * cm, lado_qr, lado_qr)

        texto_x = x + lado_qr + 0.4 * cm
        caracteres = 22
        pdf.setFont("Helvetica-Bold", 8)
        pdf.drawString(texto_x, y + alto - 0.9 * cm, _recortar(titulo, caracteres))
        pdf.setFont("Helvetica", 7)
        pdf.drawString(texto_x, y + alto - 1.4 * cm, _recortar(subtitulo, caracteres))
        pdf.setFont("Courier", 7)
        pdf.drawString(texto_x, y + 0.5 * cm, codigo)

    pdf.save()
    return buffer.getvalue()
