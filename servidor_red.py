"""
Servidor HTTP de FRKiosko para administrar desde otra PC del local.

Solo atiende POST /admin/... mediante admin_remoto.servidor. El puerto es
distinto del de CYBERCONTROL para que los dos programas puedan convivir.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from admin_remoto import servidor as admin_remoto_servidor
from errores import registrar_error

PUERTO_SERVIDOR = 8909

_servidor = None
_TOPE_CUERPO_DESCARTADO = 64 * 1024


class _ManejadorAdminRemoto(BaseHTTPRequestHandler):
    """Recibe los pedidos de administración (POST /admin/...) y delega su
    autorización. Un GET, o un POST a otra ruta, da 404."""

    def log_message(self, formato, *args):
        pass

    def _responder_json(self, status: int, respuesta: dict):
        cuerpo = json.dumps(respuesta).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def _descartar_cuerpo(self):
        """Consume los pedidos chicos rechazados para que Windows entregue la respuesta."""
        try:
            largo = int(self.headers.get("Content-Length", 0))
            if 0 < largo <= _TOPE_CUERPO_DESCARTADO:
                self.connection.settimeout(2)
                self.rfile.read(largo)
        except (ValueError, OSError):
            pass

    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        ruta = urlparse(self.path).path
        if not ruta.startswith(admin_remoto_servidor.PREFIJO):
            self._descartar_cuerpo()
            self._responder_json(404, {"ok": False, "error": "No existe."})
            return

        try:
            largo = int(self.headers.get("Content-Length", -1))
        except ValueError:
            largo = -1
        if largo < 0 or largo > admin_remoto_servidor.TAMANO_MAXIMO_PEDIDO:
            self._responder_json(413, {"ok": False, "error": "Pedido demasiado grande."})
            return

        status, respuesta = admin_remoto_servidor.atender(
            ruta, self.rfile.read(largo), self.client_address[0]
        )
        try:
            self._responder_json(status, respuesta)
        except OSError:
            pass


def iniciar_servidor():
    """Arranca el acceso remoto sin impedir que el Kiosko abra si falla el puerto."""
    global _servidor
    try:
        _servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO_SERVIDOR), _ManejadorAdminRemoto)
    except OSError as error:
        registrar_error(error, "Administración remota: abrir puerto")
        return None
    threading.Thread(target=_servidor.serve_forever, daemon=True).start()
    return _servidor
