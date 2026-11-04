"""
tests/test_estilo_ui.py
=========================
El aspecto del programa (se prueba sin abrir ninguna ventana, plataforma "offscreen"
de Qt): que se le pida a Qt el esquema de color CLARO aunque Windows esté en modo
oscuro (si no, los cuadros que la hoja de estilos no pinta salen negros con la letra
oscura encima), que las tablas no muestren la numeración de filas, que la barra
oscura de arriba use sus teclas (y que Cierre de Turno no cambie de tamaño al
titilar), que el inicio tenga la foto de fondo sin deformarla, con el título y los
siete accesos en un panel oscuro (Tareas del Turno tampoco cambia de tamaño al
titilar), y que los avisos que abren las ventanas del diseño nuevo no hereden su
estilo.

Se ejecutan con:

    python -m unittest discover tests
"""

import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtGui import QPalette, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QDialog, QFrame, QLabel, QLineEdit, QPushButton, QStyle,
    QStyleOptionFrame, QTableWidgetItem, QVBoxLayout,
)

import dominio  # noqa: E402
import main as programa  # noqa: E402
from repositories import usuarios_repo  # noqa: E402
from ui.login_window import LoginWindow  # noqa: E402
from ui.main_window import (  # noqa: E402
    COLOR_SIN_FONDO, MARGEN_DEL_PANEL, RUTA_FONDO_INICIO, FondoDelInicio, MainWindow,
)
from ui.utils import crear_tabla, icono_de_emoji  # noqa: E402
from ui.caja_window import CajaWindow, CierreTurnoWindow  # noqa: E402
from base import BaseConBaseTemporal  # noqa: E402

_app = QApplication.instance() or QApplication([])

ACCESOS_DEL_INICIO = ["VENTA DE MERCADERÍA", "IMPRESIONES", "CAJA", "GESTIÓN IMPRESIONES", "PEDIDOS DE CLIENTES",
                      "TAREAS DEL TURNO", "RANKING DE ROTACIÓN"]


def _regla(selector: str) -> dict:
    """Las propiedades de `selector { ... }` en la hoja de estilos del programa."""
    cuerpo = programa.HOJA_DE_ESTILOS.split(selector + " {", 1)[1].split("}", 1)[0]
    propiedades = (linea.strip().rstrip(";").split(":", 1) for linea in cuerpo.splitlines() if ":" in linea)
    return {nombre.strip(): valor.strip() for nombre, valor in propiedades}


class TestAspectoDelPrograma(BaseConBaseTemporal):
    def test_aplicar_estilo_fija_el_esquema_claro_y_la_hoja_de_estilos(self):
        # La plataforma "offscreen" de las pruebas no aplica el esquema de color, así
        # que acá se verifica lo que se le pide a Qt (en Windows real se comprobó
        # dibujando las pantallas: con el modo oscuro puesto, los cuadros que la hoja de
        # estilos no pinta salían negros).
        app = mock.Mock()

        programa.aplicar_estilo(app)

        app.setStyle.assert_called_once_with("Fusion")
        app.styleHints.return_value.setColorScheme.assert_called_once_with(Qt.ColorScheme.Light)
        app.setStyleSheet.assert_called_once_with(programa.HOJA_DE_ESTILOS)

    def test_las_tablas_no_muestran_la_numeracion_de_filas(self):
        tabla = crear_tabla(["Nombre", "Precio"])
        self.addCleanup(tabla.deleteLater)

        self.assertFalse(tabla.verticalHeader().isVisible())

    def test_la_pantalla_de_ingreso_se_llama_frkiosko(self):
        # El dueño quiere la marca como título de la primera pantalla, no "Sistema
        # de Kiosko" (aunque README y CLAUDE.md lo digan), y escrita igual en la
        # barra de la ventana.
        ventana = LoginWindow(lambda usuario: None)
        self.addCleanup(ventana.deleteLater)

        textos = [etiqueta.text() for etiqueta in ventana.findChildren(QLabel)]

        self.assertIn("FRKiosko", textos)
        self.assertNotIn("Sistema de Kiosko", textos)
        self.assertNotIn("CyberBIOS", textos)
        self.assertEqual(ventana.windowTitle(), "FRKiosko - Ingreso")

    def test_la_barra_de_la_ventana_principal_dice_frkiosko_con_el_nombre_y_el_rol(self):
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)

        self.assertEqual(ventana.windowTitle(), f"FRKiosko - Admin ({dominio.ROL_ADMIN})")

    def test_la_barra_de_arriba_usa_teclas_de_barra_salvo_vender_y_operador(self):
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)

        barra = ventana.findChild(QFrame, "encabezadoInicio")
        clases = {b.text().strip(): b.property("clase") for b in barra.findChildren(QPushButton)}

        # Se llamó "CERRAR SESIÓN" y después "CAMB OPERADOR" (pedidos del dueño, 2026-10-23 y 24).
        self.assertEqual(clases["OPERADOR"], "peligro")
        self.assertNotIn("CERRAR SESIÓN", clases)
        self.assertNotIn("CAMB OPERADOR", clases)
        self.assertEqual(clases["🛒  VENDER"], "primario")
        otros = [clase for texto, clase in clases.items() if texto not in ("OPERADOR", "🛒  VENDER")]
        self.assertTrue(otros and all(clase == "barra" for clase in otros), clases)

    def test_operador_vuelve_al_ingreso(self):
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        al_cerrar = []
        ventana = MainWindow(admin, lambda: al_cerrar.append(True))
        self.addCleanup(ventana.deleteLater)

        barra = ventana.findChild(QFrame, "encabezadoInicio")
        next(b for b in barra.findChildren(QPushButton) if b.text().strip() == "OPERADOR").click()
        self.assertEqual(al_cerrar, [True])

    def test_el_dibujito_de_operador_es_un_25_por_ciento_mas_grande(self):
        # Pedido del dueño (2026-10-24): el 🔄 que eligió, un 25% más grande que los dibujitos de
        # los otros botones (que miden lo que la letra). Va como ícono, no en el texto. Se mira el
        # tamaño que se pide y no lo dibujado: la plataforma "offscreen" no tiene la letra de los
        # emojis (con la de Windows, 13 px dan 13 de alto y 16,25 px dan 17; foto en el mostrador).
        pedidos = []

        def icono_anotado(emoji, tamano_px):
            pedidos.append((emoji, tamano_px))
            return icono_de_emoji(emoji, tamano_px)

        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        with mock.patch("ui.main_window.icono_de_emoji", icono_anotado):
            ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)

        barra = ventana.findChild(QFrame, "encabezadoInicio")
        operador = next(b for b in barra.findChildren(QPushButton) if b.text().strip() == "OPERADOR")
        clave = next(b for b in barra.findChildren(QPushButton) if b.text().endswith("CLAVE"))
        self.assertFalse(operador.icon().isNull())
        self.assertNotIn("🔄", operador.text())
        # Los accesos de la pantalla de inicio piden los suyos (2026-11-02): acá cuenta solo la barra.
        pedidos = [pedido for pedido in pedidos if pedido[0] == "🔄"]
        self.assertEqual(pedidos, [("🔄", clave.fontInfo().pixelSize() * 1.25)])
        self.assertEqual(operador.iconSize(), icono_de_emoji(*pedidos[0])[1])

    def test_los_accesos_del_inicio_van_uno_debajo_del_otro_y_miden_igual(self):
        # Pedido del dueño (2026-11-02, con un dibujo): Venta de Mercadería, Impresiones y Caja
        # como botones iguales, apilados a la izquierda y a la misma distancia; ese mismo día
        # se sumó Gestión Impresiones abajo, el 2026-11-03 Pedidos de Clientes y Tareas
        # del Turno, y el 2026-11-04 Ranking de Rotación.
        # Con la hoja de estilos: la letra del título y de la frase de arriba está ahí.
        self._con_la_hoja_de_estilos()
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        ventana.resize(1400, 1000)
        ventana.show()
        _app.processEvents()

        accesos = [b for b in ventana.findChildren(QPushButton) if b.objectName() == "accesoInicio"]
        self.assertEqual([b.accessibleName() for b in accesos], ACCESOS_DEL_INICIO)
        # Que los siete entren en la pantalla del mostrador: abre maximizada en 1920 x 1080, y
        # sin la barra de Windows (~40) ni la de título (~31) quedan ~1009 px. Con la letra de
        # Windows el inicio mide ~20 px más que acá (offscreen): 933 contra 914 el 2026-11-03,
        # con el panel sobre la foto de fondo y cinco accesos. Con el sexto, cada acceso pasó
        # de 110 a 98 de alto y de 20 a 14 entre uno y otro: 942 acá (~962 en Windows). Con
        # el séptimo (2026-11-04), a 86 de alto y 10 entre uno y otro.
        self.assertLessEqual(ventana.minimumSizeHint().height(), 1009 - 25)
        self.assertEqual(len({(b.width(), b.height()) for b in accesos}), 1)
        self.assertEqual(len({b.x() for b in accesos}), 1)
        arriba = [b.y() for b in accesos]
        self.assertEqual(arriba, sorted(arriba))
        self.assertEqual(len({abajo - encima for encima, abajo in zip(arriba, arriba[1:])}), 1)
        por_nombre = {b.accessibleName(): b for b in accesos}
        # PEDIDOS DE CLIENTES y TAREAS DEL TURNO abren su ventana (y, como Gestión
        # Impresiones, solo en el mostrador).
        for nombre, ventana_que_abre in (("PEDIDOS DE CLIENTES", "VentanaPedidosClientes"),
                                         ("TAREAS DEL TURNO", "VentanaTareasTurno")):
            with self.subTest(nombre):
                with mock.patch(f"ui.main_window.{ventana_que_abre}") as abierta:
                    por_nombre[nombre].click()
                abierta.assert_called_once_with(admin, ventana)
                abierta.return_value.exec.assert_called_once()
                with mock.patch(f"ui.main_window.{ventana_que_abre}") as abierta, \
                        mock.patch("ui.main_window.modo_remoto.es_copia_remota", return_value=True), \
                        mock.patch("ui.utils.mostrar_info") as aviso:
                    por_nombre[nombre].click()
                abierta.assert_not_called()
                aviso.assert_called_once()

    def test_tareas_del_turno_no_cambia_de_tamano_al_titilar(self):
        # Mientras haya tareas atrasadas, el acceso titila en rojo (2026-11-03). Como
        # Cierre de Turno en la barra: el rojo lleva los mismos bordes y relleno que el
        # azul de siempre, o el botón crecería y empujaría a los de abajo cada vez.
        azul = _regla("QPushButton#accesoInicio")
        rojo = _regla('QPushButton#accesoInicio[alerta="true"]')
        for propiedad in ("padding", "border-radius"):
            self.assertEqual(rojo[propiedad], azul[propiedad], propiedad)
        for propiedad in ("border", "border-bottom"):
            self.assertEqual(rojo[propiedad].split()[:2], azul[propiedad].split()[:2], propiedad)

        self._con_la_hoja_de_estilos()
        empleada = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Carla", "1234", dominio.ROL_EMPLEADA))
        ventana = MainWindow(empleada, lambda: None)
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        ventana.show()
        _app.processEvents()
        acceso = ventana.acceso_tareas
        self.assertEqual(acceso.accessibleName(), "TAREAS DEL TURNO")
        antes, alto_antes = acceso.size(), ventana.minimumSizeHint().height()
        ventana._poner_tareas_atrasadas(3)
        for encendido in (True, False, True):
            ventana._parpadear()
            _app.processEvents()
            self.assertEqual(bool(acceso.property("alerta")), encendido)
            self.assertEqual(acceso.size(), antes)
            self.assertEqual(ventana.minimumSizeHint().height(), alto_antes)
        # El numerito amarillo dice cuántas son, arriba a la derecha y adentro del botón.
        self.assertEqual(acceso.insignia.text(), "3")
        self.assertFalse(acceso.insignia.isHidden())
        self.assertTrue(acceso.rect().contains(acceso.insignia.geometry()))
        # Sin atrasadas deja de titilar y el numerito se va.
        ventana._poner_tareas_atrasadas(0)
        ventana._parpadear()
        ventana._parpadear()
        self.assertFalse(acceso.property("alerta"))
        self.assertTrue(acceso.insignia.isHidden())

    def _con_la_hoja_de_estilos(self):
        """La hoja de estilos del programa mientras dura la prueba (este archivo no la
        pone de entrada: el resto de las pruebas miran lo que arma cada pantalla)."""
        self.addCleanup(_app.setStyleSheet, _app.styleSheet())
        _app.setStyleSheet(programa.HOJA_DE_ESTILOS)

    def _fondo_dibujado(self, ancho=1400, alto=1000):
        """La ventana principal de un Admin, con la hoja de estilos, pedida de `ancho` x
        `alto`: su fondo y lo que dibuja. En "offscreen" la barra de arriba la ensancha
        más de lo pedido (sin la letra de Windows, sus textos salen más anchos)."""
        self._con_la_hoja_de_estilos()
        # Un Admin nuevo por ventana: no puede haber dos usuarios activos con el mismo nombre.
        self._ventanas_abiertas = getattr(self, "_ventanas_abiertas", 0) + 1
        admin = usuarios_repo.obtener_usuario(
            usuarios_repo.crear_usuario(f"Admin {self._ventanas_abiertas}", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)
        self.addCleanup(ventana.close)
        ventana.resize(ancho, alto)
        ventana.show()
        _app.processEvents()
        fondo = ventana.centralWidget()
        return ventana, fondo, fondo.grab().toImage()

    @staticmethod
    def _diferencia_con_la_foto(dibujo, fondo, zona):
        """Cuánto se aparta lo dibujado de la foto bien puesta (agrandada hasta cubrir
        todo y centrada), en promedio por canal, mirando `zona` (un QRect en puntos de la
        ventana) cada 7 puntos. 0 es la foto tal cual."""
        escala = dibujo.devicePixelRatio()
        esperada = QPixmap(str(RUTA_FONDO_INICIO)).scaled(
            dibujo.width(), dibujo.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation).toImage()
        sobra_x = (esperada.width() - dibujo.width()) // 2
        sobra_y = (esperada.height() - dibujo.height()) // 2
        diferencias = []
        for x in range(zona.left(), zona.right(), 7):
            for y in range(zona.top(), zona.bottom(), 7):
                real = dibujo.pixelColor(round(x * escala), round(y * escala))
                foto = esperada.pixelColor(round(x * escala) + sobra_x, round(y * escala) + sobra_y)
                diferencias += [abs(real.red() - foto.red()), abs(real.green() - foto.green()),
                                abs(real.blue() - foto.blue())]
        return sum(diferencias) / len(diferencias)

    def test_la_ventana_principal_tiene_de_fondo_la_foto_sin_deformarla(self):
        # Pedido del dueño (2026-11-03): la foto del kiosko de noche de fondo en toda la
        # ventana. Se mira la mitad derecha (lejos del panel, debajo de la barra) en una
        # ventana más angosta que la foto (se recortan los costados) y en una más ancha
        # (se recorta arriba y abajo): estirada o sin centrar se aparta 20 o más.
        self.assertFalse(QPixmap(str(RUTA_FONDO_INICIO)).isNull(), RUTA_FONDO_INICIO)
        for ancho, alto in ((1400, 1300), (1920, 900)):
            with self.subTest(ancho=ancho, alto=alto):
                ventana, fondo, dibujo = self._fondo_dibujado(ancho, alto)
                self.assertIsInstance(fondo, FondoDelInicio)
                zona = QRect(fondo.width() // 2, 150, fondo.width() // 2 - 10, fondo.height() - 160)
                self.assertLess(self._diferencia_con_la_foto(dibujo, fondo, zona), 3)

    def test_el_titulo_y_los_accesos_van_en_un_panel_oscuro_arriba_a_la_izquierda(self):
        # Sueltos sobre la foto, el título y la frase caían encima de los paquetes del
        # estante y no se leían: van en un panel oscuro medio transparente, del tamaño de
        # lo que tiene adentro, y con letra clara.
        ventana, fondo, dibujo = self._fondo_dibujado()

        panel = ventana.findChild(QFrame, "panelInicio")
        accesos = panel.findChildren(QPushButton)
        self.assertEqual([b.accessibleName() for b in accesos], ACCESOS_DEL_INICIO)
        self.assertEqual(panel.size(), panel.sizeHint())
        self.assertEqual(panel.pos(), QPoint(MARGEN_DEL_PANEL, MARGEN_DEL_PANEL))
        for nombre, minimo in (("tituloInicio", 200), ("detalleInicio", 150)):
            etiqueta = panel.findChild(QLabel, nombre)
            etiqueta.ensurePolished()
            self.assertGreater(etiqueta.palette().color(QPalette.WindowText).lightness(), minimo, nombre)
        # Al lado de los accesos, adentro del panel, la foto se ve oscurecida (transparente
        # daría 0: ahí no hay nada más dibujado).
        arriba_izquierda = panel.mapTo(fondo, QPoint(accesos[0].geometry().right() + 10, accesos[0].y()))
        abajo_derecha = panel.mapTo(fondo, QPoint(panel.width() - 10, accesos[-1].geometry().bottom()))
        zona = QRect(arriba_izquierda, abajo_derecha)
        self.assertGreater(zona.width(), 20)
        self.assertGreater(self._diferencia_con_la_foto(dibujo, fondo, zona), 10)

    def test_la_foto_se_agranda_a_los_puntos_reales_de_la_pantalla(self):
        # Con Windows al 125%, agrandada al tamaño "lógico" de la ventana saldría borrosa.
        with mock.patch.object(FondoDelInicio, "devicePixelRatioF", return_value=1.25):
            ventana, fondo, dibujo = self._fondo_dibujado()

        self.assertEqual(FondoDelInicio._agrandada_para, (round(fondo.width() * 1.25), round(fondo.height() * 1.25)))

    def test_la_foto_agrandada_es_una_sola_para_todo_el_programa(self):
        # La ventana del Admin, ya cerrada, sigue viva (VueltaDelAdmin la tiene agarrada):
        # con una copia agrandada por ventana, cada salida del Admin dejaba ~8 MB en memoria.
        # Desde cero, como al abrir el programa: si no, las dos usarían la que dejó otra prueba.
        with mock.patch.object(FondoDelInicio, "_agrandada", None), \
                mock.patch.object(FondoDelInicio, "_agrandada_para", None):
            _, uno, _ = self._fondo_dibujado()
            _, otro, _ = self._fondo_dibujado()
            self.assertIsNotNone(FondoDelInicio._agrandada)

        for fondo in (uno, otro):
            self.assertNotIn("_agrandada", vars(fondo))

    def test_sin_la_foto_el_fondo_es_azul_oscuro_y_no_se_rompe(self):
        # Si alguna vez faltara assets/fondo_inicio.jpg: el título es claro y sobre el
        # gris de siempre no se leería.
        with mock.patch.object(FondoDelInicio, "_foto", QPixmap()):
            ventana, fondo, dibujo = self._fondo_dibujado()

        escala = dibujo.devicePixelRatio()
        punto = dibujo.pixelColor(round((fondo.width() - 40) * escala), round((fondo.height() - 40) * escala))
        self.assertEqual(punto.name(), COLOR_SIN_FONDO.lower())

    def test_operador_va_pegado_a_la_derecha_de_lista_de_compras(self):
        # Pedido del dueño (2026-10-23): antes iba solo en la punta derecha y con
        # la pantalla de 1920 del mostrador quedaba lejos de todo. Iba pegado a
        # Clave hasta que el 2026-10-31 entró Lista de Compras en el medio.
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)
        ventana.setAttribute(Qt.WA_DontShowOnScreen)
        ventana.resize(1920, 1000)
        ventana.show()
        self.addCleanup(ventana.hide)
        _app.processEvents()

        barra = ventana.findChild(QFrame, "encabezadoInicio")
        botones = {b.text(): b for b in barra.findChildren(QPushButton)}
        lista = next(boton for texto, boton in botones.items() if texto.endswith("LISTA DE COMPRAS"))
        operador = botones["   OPERADOR"]
        hueco = operador.geometry().left() - lista.geometry().right()
        self.assertTrue(0 < hueco < 20, hueco)
        self.assertEqual(max(b.geometry().right() for b in botones.values()), operador.geometry().right())

    def test_los_botones_de_la_barra_de_arriba_van_en_mayuscula_y_negrita(self):
        # Pedido del dueño (2026-10-22).
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)

        textos = [b.text() for b in ventana.findChild(QFrame, "encabezadoInicio").findChildren(QPushButton)]

        self.assertTrue(textos)
        self.assertTrue(all(texto == texto.upper() for texto in textos), textos)
        for selector in ('QPushButton[clase="barra"]', '#encabezadoInicio QPushButton[clase="primario"]',
                         '#encabezadoInicio QPushButton[clase="peligro"]', 'QPushButton[clase="alerta"]'):
            self.assertEqual(_regla(selector)["font-weight"], "700", selector)

    def test_cierre_de_turno_no_cambia_de_tamano_al_titilar(self):
        # Barra oscura (2026-10-19): el rojo de "alerta" lleva los mismos bordes,
        # relleno y letra que "barra". Antes la letra pasaba a negrita y el botón
        # crecía 4 px y empujaba a los de al lado cada vez que titilaba (medido con la
        # pantalla real de Windows; acá, sin pantalla, las letras miden lo mismo en
        # negrita, así que se comparan las reglas de la hoja de estilos).
        barra = _regla('QPushButton[clase="barra"]')
        alerta = _regla('QPushButton[clase="alerta"]')

        self.assertEqual(alerta["font-weight"], barra["font-weight"])
        self.assertEqual(alerta["padding"], barra["padding"])
        self.assertEqual(alerta["border"].split()[0], barra["border"].split()[0])
        self.assertEqual(alerta["border-bottom"].split()[0], barra["border-bottom"].split()[0])

    def test_la_barra_de_arriba_dice_operador_y_el_nombre_sin_saludo_ni_rol(self):
        # Pedido del dueño (2026-10-16): "Operador: TOBY", no "Hola, TOBY · EMPLEADA".
        empleada = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("TOBY", "1234", dominio.ROL_EMPLEADA))
        ventana = MainWindow(empleada, lambda: None)
        self.addCleanup(ventana.deleteLater)

        barra = ventana.findChild(QFrame, "encabezadoInicio")
        textos = [etiqueta.text() for etiqueta in barra.findChildren(QLabel)]

        self.assertIn("Operador: TOBY", textos)
        self.assertFalse(any("Hola" in texto or dominio.ROL_EMPLEADA in texto for texto in textos), textos)

    def test_el_admin_figura_como_administrador_y_la_barra_va_en_dos_renglones(self):
        # Pedido del dueño (2026-10-18): arriba quién está y la caja; abajo los botones
        # desde Vender, con nombres cortos ("Admin Kiosko", "Config ADMIN").
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Sergio", "1234", dominio.ROL_ADMIN))
        ventana = MainWindow(admin, lambda: None)
        self.addCleanup(ventana.deleteLater)

        barra = ventana.findChild(QFrame, "encabezadoInicio")

        titulo = next(e for e in barra.findChildren(QLabel) if e.text() == "Administrador: Sergio")
        botones = {boton.text(): boton for boton in barra.findChildren(QPushButton)}
        for texto in ("🖨️  IMPRESIONES", "🛠️  ADMIN KIOSKO", "⚙️  CONFIG ADMIN"):
            self.assertIn(texto, botones)
        ventana.resize(1340, 700)
        ventana.show()
        QApplication.processEvents()
        self.addCleanup(ventana.close)
        vender = botones["🛒  VENDER"]
        # Los botones van debajo del nombre, Vender primero a la izquierda.
        self.assertGreater(vender.mapTo(barra, vender.rect().topLeft()).y(), titulo.mapTo(barra, titulo.rect().topLeft()).y())
        self.assertLessEqual(vender.mapTo(barra, vender.rect().topLeft()).x(), titulo.mapTo(barra, titulo.rect().topLeft()).x())

    def test_el_numero_entra_en_la_celda_que_se_esta_escribiendo(self):
        # Reportado por el dueño (2026-10-20): en ORDENAR Stock, al escribir el stock, el
        # número se veía como una rayita. El campo que abre la celda tenía el relleno de
        # todos los campos y en un renglón de tabla le quedaba ~1 px a la letra.
        self.addCleanup(_app.setStyleSheet, _app.styleSheet())
        _app.setStyleSheet(programa.HOJA_DE_ESTILOS)
        tabla = crear_tabla(["Código", "Stock"])
        self.addCleanup(tabla.deleteLater)
        tabla.setEditTriggers(QAbstractItemView.DoubleClicked)
        tabla.insertRow(0)
        for columna, texto in enumerate(("COCA", "54")):
            tabla.setItem(0, columna, QTableWidgetItem(texto))
        tabla.resize(400, 200)
        tabla.show()
        _app.processEvents()

        tabla.editItem(tabla.item(0, 1))
        _app.processEvents()
        campo = next(c for c in tabla.viewport().findChildren(QLineEdit) if c.isVisible())
        opcion = QStyleOptionFrame()
        campo.initStyleOption(opcion)
        lugar_para_la_letra = campo.style().subElementRect(QStyle.SE_LineEditContents, opcion, campo)

        self.assertGreaterEqual(lugar_para_la_letra.height(), campo.fontMetrics().height())

    def test_los_avisos_que_abren_las_ventanas_del_diseno_nuevo_no_heredan_su_estilo(self):
        # El diseño del 2026-10-26 (ui/piezas_ventana.py) pinta sus piezas por objectName
        # o "clase", y a las etiquetas de un panel solo con ">": los avisos y formularios
        # que se abren encima son hijos de estas ventanas y tienen que verse como siempre.
        self.addCleanup(_app.setStyleSheet, _app.styleSheet())
        _app.setStyleSheet(programa.HOJA_DE_ESTILOS)
        admin = usuarios_repo.obtener_usuario(usuarios_repo.crear_usuario("Admin", "1234", dominio.ROL_ADMIN))
        caja = CajaWindow()
        cierre = CierreTurnoWindow(admin)
        for ventana, etiqueta_propia in (
            (caja, caja.findChild(QLabel, "encabezadoTabla")),
            (cierre, cierre.findChild(QLabel, "notaCambio")),
        ):
            self.addCleanup(ventana.deleteLater)
            dialogo = QDialog(ventana)
            texto_del_dialogo = QLabel("¿Confirmás el cierre?", dialogo)
            QVBoxLayout(dialogo).addWidget(texto_del_dialogo)
            for etiqueta in (etiqueta_propia, texto_del_dialogo):
                etiqueta.ensurePolished()

            letra_propia = etiqueta_propia.palette().color(QPalette.WindowText).name()
            letra_del_dialogo = texto_del_dialogo.palette().color(QPalette.WindowText).name()

            self.assertEqual(letra_del_dialogo, _regla("QWidget")["color"].lower(), ventana.windowTitle())
            self.assertNotEqual(letra_propia, letra_del_dialogo, ventana.windowTitle())  # la ventana sí, en gris


if __name__ == "__main__":
    unittest.main()
