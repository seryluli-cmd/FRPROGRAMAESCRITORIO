"""
armar_icono.py
==============
Arma assets/icono.png (256 px, el que se ve en la pantalla de ingreso) y
assets/icono.ico (el de la ventana, la barra de tareas y el .exe) a partir de
assets/icono.svg. Hay que correrlo de nuevo cada vez que se cambie el dibujo:

    python assets/armar_icono.py

Cada tamaño del .ico se dibuja aparte desde el SVG, en vez de achicar el de
256 px: así el de 16 px (el de la barra de tareas chica) sale nítido.

Usa QtSvg (viene con PySide6) para dibujar y Pillow para juntar los tamaños
en el .ico. Pillow no hace falta para usar el programa, solo para esto.
"""

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

CARPETA = Path(__file__).resolve().parent
SVG = CARPETA / "icono.svg"
PNG = CARPETA / "icono.png"
ICO = CARPETA / "icono.ico"

# Los tamaños que pide Windows (barra de tareas, Escritorio, Explorador).
TAMANOS_ICO = (16, 24, 32, 48, 64, 128, 256)


def dibujar(renderer: QSvgRenderer, lado: int) -> Image.Image:
    """El SVG dibujado en un cuadrado de `lado` px con fondo transparente."""
    imagen = QImage(lado, lado, QImage.Format_ARGB32)
    imagen.fill(Qt.transparent)
    pintor = QPainter(imagen)
    pintor.setRenderHint(QPainter.Antialiasing)
    renderer.render(pintor)
    pintor.end()
    datos = QByteArray()
    buffer = QBuffer(datos)
    buffer.open(QIODevice.WriteOnly)
    imagen.save(buffer, "PNG")
    buffer.close()
    return Image.open(io.BytesIO(bytes(datos))).convert("RGBA")


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 (QtSvg la necesita)
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"No se pudo leer {SVG}")
    imagenes = {lado: dibujar(renderer, lado) for lado in TAMANOS_ICO}
    imagenes[256].save(PNG)
    imagenes[256].save(
        ICO,
        sizes=[(lado, lado) for lado in TAMANOS_ICO],
        append_images=[imagenes[lado] for lado in TAMANOS_ICO if lado != 256],
    )
    print(f"Listo: {PNG.name} y {ICO.name} ({', '.join(str(lado) for lado in TAMANOS_ICO)} px)")


if __name__ == "__main__":
    main()
