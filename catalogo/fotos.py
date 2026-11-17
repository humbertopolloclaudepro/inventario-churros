"""Fotografías de referencia: se validan y se reducen antes de guardarlas en la base de datos."""
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

LADO_MAXIMO = 1024
CALIDAD_JPEG = 80
TAMANO_MAXIMO_SUBIDA = 10 * 1024 * 1024  # 10 MB, por si la app no pudo reducirla antes
FORMATOS = {"JPEG", "PNG", "WEBP", "HEIF", "MPO"}


class FotoInvalida(Exception):
    """La imagen no se puede usar; el mensaje se muestra al usuario."""


def preparar_foto(archivo):
    """Devuelve la foto como JPEG reducido (bytes). Corrige la rotación y quita los metadatos."""
    if archivo.size > TAMANO_MAXIMO_SUBIDA:
        raise FotoInvalida("La foto pesa más de 10 MB. Toma otra con menor resolución.")
    try:
        imagen = Image.open(archivo)
        if imagen.format not in FORMATOS:
            raise FotoInvalida("Formato no válido. Usa una foto JPG o PNG.")
        imagen = ImageOps.exif_transpose(imagen)
        imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
        if imagen.mode != "RGB":
            fondo = Image.new("RGB", imagen.size, "white")
            fondo.paste(imagen, mask=imagen.convert("RGBA").split()[-1])
            imagen = fondo
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise FotoInvalida("El archivo no es una imagen válida.")
    salida = BytesIO()
    imagen.save(salida, "JPEG", quality=CALIDAD_JPEG, optimize=True)
    return salida.getvalue()
