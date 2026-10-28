"""
ui/hoja_de_estilos.py
=====================
La hoja de estilos Qt de TODO el programa (`HOJA_DE_ESTILOS`). La aplica
`main.aplicar_estilo(app)`, junto con el estilo Fusion y el esquema de color claro.

Estaba en main.py y se mudó acá el 2026-10-22 (revisión de limpieza: main.py pasaba
las 600 líneas, regla 12 de CLAUDE.md), sin cambiar nada. Es solo texto: no importa
nada del programa.
"""

from pathlib import Path

# Qt QSS quiere barras "/" en las rutas de imagen (incluso en Windows) y
# no admite f-strings acá abajo (la hoja de estilos ya usa { } para CSS),
# por eso el path se arma aparte y se reemplaza con .replace() al final.
# La carpeta assets está junto al código, un nivel arriba de ui/ (igual que
# el ícono de ui/login_window.py).
RUTA_FLECHA_ABAJO = (Path(__file__).resolve().parent.parent / "assets" / "flecha_abajo.svg").as_posix()


# --------------------------------------------------------------------
# Estilo visual
# --------------------------------------------------------------------
# Estilo visual general de todo el programa: paleta de color consistente
# (azul para la acción principal de cada pantalla, bordó para lo
# destructivo/cerrar sesión, verde para confirmaciones), tipografía más
# grande y botones con más espacio interno, pensado para que sea cómodo
# de usar rápido con mouse o con pantalla táctil detrás de un mostrador.
#
# Los botones "importantes" de cada pantalla se marcan en el código con
# boton.setProperty("clase", "primario") (acción principal, ej. Cobrar,
# Guardar) o "peligro" (acción destructiva, ej. Cancelar, Borrar, Cerrar
# sesión) — eso es lo que activa los selectores QPushButton[clase=...]
# de acá abajo. Sin esa propiedad, un botón usa el estilo neutro de
# siempre.
HOJA_DE_ESTILOS = """
    QWidget {
        font-family: "Segoe UI";
        font-size: 13px;
        color: #1B2233;
    }
    QMainWindow, QDialog {
        background-color: #EEF1F6;
    }
    QPushButton {
        background-color: #FFFFFF;
        border: 1px solid #CDD3DE;
        padding: 9px 18px;
        border-radius: 8px;
        color: #1B2233;
    }
    QPushButton:hover {
        background-color: #F5F7FA;
        border-color: #B7BFCC;
    }
    QPushButton:pressed {
        background-color: #E7EAF0;
    }
    QPushButton:disabled {
        color: #A7ADB8;
        background-color: #F5F6F8;
        border-color: #E1E4E9;
    }
    QPushButton:checked {
        background-color: #2F6FED;
        border: 1px solid #2F6FED;
        color: #FFFFFF;
        font-weight: 600;
    }
    QPushButton:checked:hover {
        background-color: #255BC7;
        border-color: #255BC7;
    }
    /* Un botón tildado dentro de un grupo deshabilitado no tiene que verse tan
       fuerte como uno activo. */
    QPushButton:checked:disabled {
        background-color: #AEC3F2;
        border: 1px solid #AEC3F2;
        color: #EFF3FE;
    }
    QPushButton[clase="primario"] {
        background-color: #2F6FED;
        border: 1px solid #2F6FED;
        color: #FFFFFF;
        font-weight: 600;
    }
    QPushButton[clase="primario"]:hover {
        background-color: #255BC7;
        border-color: #255BC7;
    }
    QPushButton[clase="primario"]:pressed {
        background-color: #1D48A0;
        border-color: #1D48A0;
    }
    QPushButton[clase="primario"]:disabled {
        background-color: #AEC3F2;
        border-color: #AEC3F2;
        color: #EFF3FE;
    }
    QPushButton[clase="peligro"] {
        background-color: #FFFFFF;
        border: 1px solid #D9838A;
        color: #A6323C;
        font-weight: 600;
    }
    QPushButton[clase="peligro"]:hover {
        background-color: #FBEAEA;
        border-color: #C96870;
    }
    QPushButton[clase="peligro"]:pressed {
        background-color: #F3D3D3;
    }
    QPushButton[clase="peligro"]:disabled {
        background-color: #F5F6F8;
        border-color: #E1E4E9;
        color: #A7ADB8;
    }
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit {
        padding: 7px 9px;
        border: 1px solid #CDD3DE;
        border-radius: 7px;
        background-color: #FFFFFF;
        selection-background-color: #2F6FED;
    }
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {
        border: 1.5px solid #2F6FED;
    }
    QLineEdit:disabled {
        background-color: #F5F6F8;
        color: #A7ADB8;
    }
    QComboBox {
        padding-right: 8px;
    }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid #CDD3DE;
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        background-color: #F5F7FA;
    }
    QComboBox::drop-down:hover {
        background-color: #EAEFF7;
    }
    QComboBox::down-arrow {
        image: url(__RUTA_FLECHA_ABAJO__);
        width: 10px;
        height: 6px;
        margin-right: 9px;
    }
    QComboBox QAbstractItemView {
        border: 1px solid #CDD3DE;
        selection-background-color: #DCE7FD;
        selection-color: #1B2233;
        outline: none;
    }
    QCheckBox {
        spacing: 8px;
        padding: 2px 0;
    }
    QCheckBox::indicator {
        width: 17px;
        height: 17px;
        border: 1.5px solid #B7BFCC;
        border-radius: 4px;
        background-color: #FFFFFF;
    }
    QCheckBox::indicator:hover {
        border-color: #2F6FED;
    }
    QCheckBox::indicator:checked {
        background-color: #2F6FED;
        border-color: #2F6FED;
    }
    QGroupBox {
        border: 1px solid #D3D8E0;
        border-radius: 8px;
        margin-top: 14px;
        padding-top: 6px;
        font-weight: 600;
        color: #3C4350;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: #3C4350;
    }
    QTableWidget {
        gridline-color: #E4E7EC;
        background-color: #FFFFFF;
        border: 1px solid #D3D8E0;
        border-radius: 8px;
        alternate-background-color: #F7F9FC;
        selection-background-color: #DCE7FD;
        selection-color: #1B2233;
    }
    QTableWidget::item {
        padding: 5px;
    }
    QHeaderView::section {
        background-color: #F5F7FA;
        padding: 9px 8px;
        border: none;
        border-bottom: 1.5px solid #D3D8E0;
        font-weight: 600;
        font-size: 11px;
        letter-spacing: 0.4px;
        color: #5B6472;
    }
    QTabWidget::pane {
        border: 1px solid #D3D8E0;
        border-radius: 8px;
        top: -1px;
        background-color: #FFFFFF;
    }
    QTabBar::tab {
        padding: 9px 20px;
        background: transparent;
        border: none;
        border-bottom: 2.5px solid transparent;
        color: #5B6472;
        margin-right: 4px;
    }
    QTabBar::tab:hover {
        color: #1B2233;
    }
    QTabBar::tab:selected {
        color: #2F6FED;
        border-bottom: 2.5px solid #2F6FED;
        font-weight: 600;
    }
    QScrollBar:vertical {
        width: 11px;
        background: #EEF1F6;
    }
    QScrollBar::handle:vertical {
        background: #C7CDD6;
        border-radius: 5px;
        min-height: 24px;
    }
    QScrollBar::handle:vertical:hover {
        background: #AEB4BF;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    #tarjetaLogin {
        background-color: #FFFFFF;
        border: 1px solid #E1E4EA;
        border-radius: 14px;
    }
    /* Barra superior oscura del mostrador. */
    #encabezadoInicio {
        background-color: #1E2330;
        border: 1px solid #2B3242;
        border-radius: 12px;
    }
    QLabel#nombreEncabezado {
        font-size: 15px;
        font-weight: 700;
        color: #F1F4F9;
    }
    QLabel#cajaEncabezado {
        font-size: 13px;
        color: #9AA4B5;
    }

    /* --- Pulido visual (2026-10-10) --- */

    /* Botones de la barra oscura de arriba (2026-10-19): cada uno es una tecla con
       relieve (el borde de abajo, más grueso y oscuro) que se prende en azul al
       pasarle el mouse y se hunde al apretarla (baja 2 px y pierde el relieve).
       Vender (primario) en azul lleno y 🔄 Operador (peligro) con borde rojo,
       pegado a la derecha de Clave. Todos en negrita y mayúscula (pedido del dueño, 2026-10-22;
       la mayúscula la pone MainWindow._agregar_boton_barra). */
    QPushButton[clase="barra"] {
        background-color: #2C3345;
        border: 1px solid #3A4358;
        border-top-color: #4B5570;
        border-bottom: 3px solid #0B0D12;
        color: #E6EAF2;
        font-weight: 700;
        padding: 7px 12px;
    }
    QPushButton[clase="barra"]:hover {
        background-color: #323B50;
        border-color: #4C8DFF;
        border-bottom-color: #1D48A0;
        color: #FFFFFF;
    }
    QPushButton[clase="barra"]:pressed,
    QPushButton[clase="alerta"]:pressed,
    #encabezadoInicio QPushButton[clase="primario"]:pressed,
    #encabezadoInicio QPushButton[clase="peligro"]:pressed {
        border-bottom-width: 1px;
        margin-top: 2px;
    }
    QPushButton[clase="barra"]:pressed {
        background-color: #252B3A;
    }
    #encabezadoInicio QPushButton[clase="primario"] {
        background-color: #2F6FED;
        border: 1px solid #4C8DFF;
        border-top-color: #7AAAFF;
        border-bottom: 3px solid #173A85;
        color: #FFFFFF;
        font-weight: 700;
        padding: 7px 16px;
    }
    #encabezadoInicio QPushButton[clase="primario"]:hover {
        background-color: #3D7BFF;
        border-color: #7AAAFF;
        border-bottom-color: #173A85;
    }
    #encabezadoInicio QPushButton[clase="primario"]:pressed {
        background-color: #255BC7;
    }
    #encabezadoInicio QPushButton[clase="peligro"] {
        background-color: transparent;
        border: 1px solid #8A3A42;
        border-bottom: 3px solid #4A1A1F;
        color: #FF8A93;
        font-weight: 700;
        padding: 7px 16px;
    }
    #encabezadoInicio QPushButton[clase="peligro"]:hover {
        background-color: #3A2328;
        border-color: #C24B57;
        border-bottom-color: #4A1A1F;
        color: #FFB3B9;
    }
    #encabezadoInicio QPushButton[clase="peligro"]:pressed {
        background-color: #2E1C20;
    }
    /* Cierre de Turno cuando toca cerrar la caja (desde 5 minutos antes del fin
       del turno, pedido del dueño 2026-10-18): titila alternando este rojo lleno
       con el estilo "barra" (ver MainWindow._parpadear). Mismos bordes, relleno y
       letra que "barra", para que el botón no cambie de tamaño al titilar. */
    QPushButton[clase="alerta"] {
        background-color: #D92D3A;
        border: 1px solid #FF5A66;
        border-top-color: #FF8A93;
        border-bottom: 3px solid #6E141C;
        color: #FFFFFF;
        font-weight: 700;
        padding: 7px 12px;
    }
    QPushButton[clase="alerta"]:hover {
        background-color: #E5404C;
    }

    /* Aviso informativo, en azul suave (no es una alarma): lo usa el Resumen del
       Día cuando un cierre de ese día quedó anotado en otro. */
    QFrame#avisoInformativo {
        background-color: #EEF4FF;
        border: 1px solid #C9D9FB;
        border-radius: 10px;
    }
    QFrame#avisoInformativo QLabel#avisoTitulo {
        color: #1D48A0;
        font-weight: 600;
    }

    /* Cuadros de texto de varias líneas: pintados acá para que no salgan oscuros
       con el modo oscuro de Windows (ver main.aplicar_estilo). */
    QTextEdit, QPlainTextEdit {
        background-color: #FFFFFF;
        border: 1px solid #D3D8E0;
        border-radius: 8px;
        padding: 6px 8px;
        color: #3C4350;
        selection-background-color: #DCE7FD;
        selection-color: #1B2233;
    }

    /* Numeración de filas y esquina de las tablas (por defecto toman el color de
       Windows); en las tablas del programa la numeración ni se muestra. */
    QHeaderView {
        background-color: #F5F7FA;
    }
    QHeaderView::section:vertical {
        background-color: #F5F7FA;
        color: #8A93A3;
        border: none;
        border-right: 1px solid #E4E7EC;
        padding: 0 8px;
    }
    QTableCornerButton::section {
        background-color: #F5F7FA;
        border: none;
    }
    QHeaderView::section:horizontal {
        text-align: left;
    }
    QTableWidget::item:selected {
        border: none;
    }
    /* El campo que se abre al escribir en una celda (el stock de ORDENAR
       Stock): con el relleno de 7 px de los demás campos, en un renglón de tabla le
       quedaba ~1 px a la letra y el número se veía como una rayita (reportado por el
       dueño, 2026-10-20). Va con ">" (campo hijo del área de la tabla) para no tocar el
       campo de adentro de un QSpinBox puesto en una celda: ese cuelga del QSpinBox, no
       de la tabla. */
    QAbstractItemView > QWidget > QLineEdit {
        padding: 0 4px;
        border-radius: 3px;
    }
    QAbstractItemView > QWidget > QLineEdit:focus {
        border: 1px solid #2F6FED;
    }

    /* Selector de fecha: mismo aspecto que el desplegable. */
    QDateEdit::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border-left: 1px solid #CDD3DE;
        border-top-right-radius: 7px;
        border-bottom-right-radius: 7px;
        background-color: #F5F7FA;
    }
    QDateEdit::drop-down:hover {
        background-color: #EAEFF7;
    }
    QDateEdit::down-arrow {
        image: url(__RUTA_FLECHA_ABAJO__);
        width: 10px;
        height: 6px;
        margin-right: 9px;
    }

    /* Menús contextuales y avisos flotantes. */
    QMenu {
        background-color: #FFFFFF;
        border: 1px solid #D3D8E0;
        border-radius: 8px;
        padding: 5px;
    }
    QMenu::item {
        padding: 8px 26px 8px 14px;
        border-radius: 6px;
    }
    QMenu::item:selected {
        background-color: #DCE7FD;
        color: #1B2233;
    }
    QMenu::separator {
        height: 1px;
        background: #E4E7EC;
        margin: 5px 8px;
    }
    QToolTip {
        background-color: #1B2233;
        color: #FFFFFF;
        border: none;
        padding: 5px 8px;
    }

    /* Carteles de aviso y confirmación: botones parejos. */
    QMessageBox QPushButton {
        min-width: 88px;
    }

    QScrollBar:horizontal {
        height: 11px;
        background: #EEF1F6;
    }
    QScrollBar::handle:horizontal {
        background: #C7CDD6;
        border-radius: 5px;
        min-width: 24px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #AEB4BF;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    /* Venta de Mercadería (ui/ventas_window.py), el diseño que eligió el dueño el
       2026-10-26 (maqueta "B"): encabezado blanco, campo de escaneo grande, teclas en
       relieve con la tecla dibujada aparte y el total oscuro a la derecha, como la
       barra de arriba de la ventana principal. */
    QFrame#encabezadoVenta {
        background-color: #FFFFFF;
        border: none;
        border-bottom: 1px solid #DDE2EA;
    }
    QLabel#tituloVenta {
        font-size: 16px;
        font-weight: 700;
        color: #1E2330;
    }
    QLabel#datosVenta {
        color: #5B6475;
    }
    QLineEdit#campoEscaneo, QLineEdit#campoEscaneo:focus {
        border: 2px solid #2F6FED;
        border-radius: 9px;
        padding: 9px 8px;
        font-size: 15px;
        background-color: #FFFFFF;
    }
    QPushButton[clase="tecla"] {
        background-color: #FFFFFF;
        border: 1px solid #CDD3DE;
        border-bottom: 3px solid #AEB6C4;
        border-radius: 7px;
        padding: 6px 12px 6px 8px;
        font-weight: 700;
        color: #1B2233;
    }
    QPushButton[clase="tecla"]:hover {
        border-color: #4C8DFF;
        border-bottom-color: #2F6FED;
    }
    QPushButton[clase="tecla"]:pressed {
        border-bottom-width: 1px;
        margin-top: 2px;
        background-color: #F0F4FC;
    }
    QLabel#avisoStockVenta {
        background-color: #FDECEC;
        border: 1px solid #F1B5BA;
        border-radius: 7px;
        color: #A6323C;
        font-weight: 700;
        padding: 6px 10px;
    }
    QFrame#totalVenta {
        background-color: #1E2330;
        border: 1px solid #2B3242;
        border-radius: 10px;
    }
    QLabel#totalVentaTitulo {
        color: #8A93A3;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
    }
    QLabel#totalVentaMonto {
        color: #FFFFFF;
        font-size: 28px;
        font-weight: 700;
    }
    QLabel#totalVentaUnidades {
        color: #8A93A3;
        font-size: 12px;
    }
    QPushButton#botonCobrarVenta {
        background-color: #2F6FED;
        border: 1px solid #4C8DFF;
        border-top-color: #7AAAFF;
        border-bottom: 3px solid #173A85;
        padding: 13px 10px;
        font-size: 15px;
        font-weight: 700;
    }
    QPushButton#botonCobrarVenta:hover {
        background-color: #3D7BFF;
    }
    QPushButton#botonCobrarVenta:pressed {
        background-color: #255BC7;
        border-bottom-width: 1px;
        margin-top: 2px;
    }
    /* Configuración ADMIN, Administrar Kiosko, Caja y Cierre de Turno con el diseño que eligió el
       dueño el 2026-10-26 (maqueta "A", clara con cabecera cyber; las piezas están en
       ui/piezas_ventana.py). Todo va por objectName o "clase", nunca por tipo de widget:
       los avisos y las ventanas que se abren desde estas son hijas suyas y no tienen
       que heredar nada. */
    QFrame#cabeceraOscura {
        background-color: #1E2330;
        border: 1px solid #2B3242;
        border-radius: 12px;
    }
    QFrame#cabeceraOscura > QLabel {
        background: transparent;
    }
    QLabel#iconoCabecera {
        font-size: 26px;
    }
    QLabel#tituloCabecera {
        color: #F1F4F9;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel#detalleCabecera {
        color: #9AA4B5;
        font-size: 12px;
    }
    /* La estela: celeste que se aclara hacia la derecha (de #4C8DFF a #EAF4FF), parte
       del diseño de cabecera que eligió el dueño. */
    QFrame#estelaCabecera {
        border: none;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(76, 141, 255, 0),
            stop:0.55 rgba(76, 141, 255, 90), stop:0.92 #4C8DFF, stop:1 #EAF4FF);
    }
    QLabel#pastillaCabecera {
        border-radius: 11px;
        padding: 3px 11px;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#pastillaCabecera[tono="azul"] {
        background-color: rgba(76, 141, 255, 40);
        border: 1px solid rgba(76, 141, 255, 110);
        color: #9DC0FF;
    }
    QLabel#pastillaCabecera[tono="gris"] {
        background-color: rgba(255, 255, 255, 14);
        border: 1px solid #3A4358;
        color: #C9CED8;
    }
    QFrame#panelBlanco {
        background-color: #FFFFFF;
        border: 1px solid #DDE2EA;
        border-radius: 12px;
    }
    QFrame#panelBlanco > QLabel {
        background: transparent;
    }
    QLabel#tituloDeSeccion {
        color: #5B6472;
        font-size: 11px;
        font-weight: 700;
        padding: 2px 2px 0 2px;
    }
    /* Tarjeta de menú: botón grande con dibujito, título y para qué es. El texto lo
       dibujan etiquetas de adentro (ver ui/piezas_ventana.tarjeta_de_menu). */
    QPushButton[clase="tarjetaMenu"] {
        background-color: #FFFFFF;
        border: 1px solid #D5DBE5;
        border-bottom: 3px solid #B9C1CF;
        border-radius: 10px;
        padding: 0;
    }
    QPushButton[clase="tarjetaMenu"]:hover {
        background-color: #F7FAFF;
        border-color: #4C8DFF;
        border-bottom-color: #2F6FED;
    }
    QPushButton[clase="tarjetaMenu"]:pressed {
        background-color: #EEF3FD;
        border-bottom-width: 1px;
        margin-top: 2px;
    }
    QPushButton[clase="tarjetaMenu"]:disabled {
        background-color: #F3F5F8;
        border-color: #E1E4E9;
        border-bottom-color: #E1E4E9;
    }
    QPushButton[clase="tarjetaMenu"] > QLabel {
        background: transparent;
    }
    QLabel#iconoTarjeta {
        font-size: 21px;
    }
    QLabel#tituloTarjeta {
        font-size: 13px;
        font-weight: 700;
        color: #1B2233;
    }
    QLabel#detalleTarjeta {
        font-size: 11px;
        color: #6B7585;
    }
    QLabel#tituloTarjeta:disabled, QLabel#detalleTarjeta:disabled {
        color: #A7ADB8;
    }
    /* Teclas con relieve (como la barra y Venta): se hunden al apretarlas. */
    QPushButton[clase="teclaBlanca"], QPushButton[clase="teclaAzul"],
    QPushButton[clase="teclaVerde"], QPushButton[clase="teclaRoja"] {
        border-radius: 8px;
        padding: 7px 16px;
        font-weight: 700;
    }
    QPushButton[clase="teclaBlanca"] {
        background-color: #FFFFFF;
        border: 1px solid #CDD3DE;
        border-bottom: 3px solid #AEB6C4;
        color: #1B2233;
    }
    QPushButton[clase="teclaBlanca"]:hover {
        border-color: #4C8DFF;
        border-bottom-color: #2F6FED;
    }
    QPushButton[clase="teclaAzul"] {
        background-color: #2F6FED;
        border: 1px solid #4C8DFF;
        border-top-color: #7AAAFF;
        border-bottom: 3px solid #173A85;
        color: #FFFFFF;
    }
    QPushButton[clase="teclaAzul"]:hover {
        background-color: #3D7BFF;
    }
    QPushButton[clase="teclaVerde"] {
        background-color: #1F9D55;
        border: 1px solid #34C374;
        border-top-color: #6EE7A0;
        border-bottom: 3px solid #0F5A30;
        color: #FFFFFF;
    }
    QPushButton[clase="teclaVerde"]:hover {
        background-color: #23B062;
    }
    QPushButton[clase="teclaRoja"] {
        background-color: #FFFFFF;
        border: 1px solid #E0A3A8;
        border-bottom: 3px solid #C9727B;
        color: #A6323C;
    }
    QPushButton[clase="teclaRoja"]:hover {
        background-color: #FBEAEA;
        border-color: #C96870;
    }
    QPushButton[clase="teclaBlanca"]:pressed, QPushButton[clase="teclaAzul"]:pressed,
    QPushButton[clase="teclaVerde"]:pressed, QPushButton[clase="teclaRoja"]:pressed {
        border-bottom-width: 1px;
        margin-top: 2px;
    }
    QPushButton[clase="teclaBlanca"]:disabled, QPushButton[clase="teclaRoja"]:disabled,
    QPushButton[clase="teclaAzul"]:disabled, QPushButton[clase="teclaVerde"]:disabled {
        background-color: #F5F6F8;
        border-color: #E1E4E9;
        border-bottom-color: #E1E4E9;
        color: #A7ADB8;
    }
    /* Caja y Cierre de Turno (y el detalle de un cierre en Control de Cierres) con el
       mismo diseño, 2026-10-26 (ui/tarjeta_cierre.py). Las cifras grandes: la verde es
       el efectivo del cajón o del sobre, la azul el TOTAL (los colores que eligió el
       dueño el 2026-10-20). */
    QFrame#cifraDestacada {
        border-radius: 12px;
    }
    QFrame#cifraDestacada[tono="verde"] {
        background-color: #ECF8F0;
        border: 1px solid #BCE3CA;
    }
    QFrame#cifraDestacada[tono="azul"] {
        background-color: #EDF3FF;
        border: 1px solid #C4D6F8;
    }
    QFrame#cifraDestacada > QLabel {
        background: transparent;
    }
    /* La barra "ENVIANDO CIERRE DE TURNO" (ui/envio_pwa_progreso.py): azul mientras
       se manda; el título en verde si llegó y en rojo si no se pudo. */
    QProgressBar#barraEnvio {
        background-color: #EDF3FF;
        border: 1px solid #C4D6F8;
        border-radius: 8px;
    }
    QProgressBar#barraEnvio::chunk {
        background-color: #2F6FED;
        border-radius: 7px;
    }
    QLabel#tituloEnvio {
        color: #1D4FA8;
        font-size: 16px;
        font-weight: 800;
        letter-spacing: 1px;
    }
    QLabel#tituloEnvio[estado="enviado"] { color: #1E9E50; }
    QLabel#tituloEnvio[estado="error"] { color: #C62828; }
    QLabel#detalleEnvio { color: #5A6F96; }
    QLabel#tituloCifra {
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#valorCifra {
        font-size: 30px;
        font-weight: 700;
    }
    QLabel#aclaracionCifra {
        font-size: 11px;
    }
    QFrame#cifraDestacada[tono="verde"] > QLabel#tituloCifra { color: #1D6B3D; }
    QFrame#cifraDestacada[tono="verde"] > QLabel#valorCifra { color: #1E9E50; }
    QFrame#cifraDestacada[tono="verde"] > QLabel#aclaracionCifra { color: #4F7A60; }
    QFrame#cifraDestacada[tono="azul"] > QLabel#tituloCifra { color: #1D4FA8; }
    QFrame#cifraDestacada[tono="azul"] > QLabel#valorCifra { color: #2F6FED; }
    QFrame#cifraDestacada[tono="azul"] > QLabel#aclaracionCifra { color: #5A6F96; }
    /* La tabla de dónde vino la plata: un renglón por negocio, efectivo y digital en
       columnas; el que está en cero, apagado. */
    QLabel#encabezadoTabla {
        color: #8A93A3;
        font-size: 11px;
        font-weight: 700;
        padding: 2px 0 6px 0;
    }
    QLabel#iconoNegocio {
        font-size: 15px;
    }
    QLabel#nombreNegocio, QLabel#montoNegocio {
        color: #1B2233;
        font-size: 13px;
        padding: 6px 0;
    }
    QLabel#montoNegocio {
        font-weight: 600;
    }
    QLabel#nombreNegocio[vacio="true"], QLabel#montoNegocio[vacio="true"] {
        color: #A9B0BC;
        font-weight: 400;
    }
    QFrame#lineaRenglon {
        background-color: #EEF1F5;
        border: none;
    }
    QFrame#lineaTotal {
        background-color: #1E2330;
        border: none;
    }
    QLabel#nombreTotal, QLabel#montoTotal {
        color: #1B2233;
        font-weight: 700;
        padding: 8px 0;
    }
    QLabel#nombreTotal {
        font-size: 13px;
    }
    QLabel#montoTotal {
        font-size: 15px;
    }
    QLabel#nombreCambio, QLabel#montoCambio {
        color: #3C4350;
        font-size: 13px;
        padding: 7px 0 0 0;
    }
    QLabel#notaCambio {
        color: #8A93A3;
        font-size: 11px;
        padding: 0 0 2px 0;
    }
    QLabel#notaCierre {
        background-color: #F6F8FB;
        border: 1px solid #E1E5EC;
        border-radius: 10px;
        color: #5B6472;
        font-size: 12px;
        padding: 8px 12px;
    }
    QLabel#notaCierre[alerta="true"] {
        background-color: #FDEEEF;
        border-color: #F1B9BE;
        color: #B0242F;
        font-weight: 600;
    }

""".replace("__RUTA_FLECHA_ABAJO__", RUTA_FLECHA_ABAJO)
