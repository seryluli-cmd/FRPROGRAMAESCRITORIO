"""
tests/test_envio_pwa_tareas.py
================================
Las TAREAS DEL TURNO que viajan con cada Cierre de Turno a la app de gastos
(repositories/tareas_del_cierre_repo.py y envio_pwa_repo.datos_del_cierre; pedido
del dueño, 2026-11-03: que se vean abajo del resumen de caja, que queda intacto):
qué tareas son de un cierre (las de su ventana, ni las del cierre anterior ni las
que tocan después), cómo van (hechas con quién y a qué hora; sin hacer con quiénes
la pospusieron) y que el cierre queda como estaba al cerrar aunque después marquen,
cambien o borren la tarea.

Usa la base y la app de mentira de tests/test_envio_pwa.py: ninguna prueba sale a
internet.

Se ejecutan con:

    python -m unittest discover tests
"""

import json
import unittest
from datetime import timedelta

import dominio
from repositories import envio_pwa_repo, relevo_repo, tareas_turno_repo, turnos_repo
from test_envio_pwa import LUNES, MARTES, _a_las, _BaseDeEnvios

MIERCOLES = MARTES + timedelta(days=1)
TODOS = dominio.TAREA_TODOS_LOS_DIAS


class _ConTareas(_BaseDeEnvios):
    def _tarea(self, texto, hora):
        """Una tarea de todos los días, cargada por el Admin el lunes a las 05:00 (la
        Noche del domingo): toca desde el lunes a las 05:00. Cargada antes, la del
        domingo a las 19:30 iría en el primer cierre, que cubre desde el principio."""
        return tareas_turno_repo.crear_tarea(self.admin_id, texto, hora, TODOS, ahora=_a_las(5, 0))

    def _cierre_de_toby(self, a_las=_a_las(14, 0)):
        """La caja de TOBY del lunes (abierta a las 05:55), cerrada por ella."""
        self._turno_de_toby()
        return turnos_repo.cerrar_turno(self.toby_id, ahora_dt=a_las)

    def _tareas(self, cierre_id):
        return self._datos(cierre_id)["tareas"]

    def _resumen(self, cierre_id):
        return [(t["dia"], t["hora"], t["texto"], t["hecha"]) for t in self._tareas(cierre_id)]


class TestQueTareasSonDelCierre(_ConTareas):
    def test_van_las_de_su_ventana_en_el_orden_del_turno(self):
        self._tarea("REPONER LA HELADERA", "11:00")
        self._tarea("CONTAR EL CAMBIO", "07:00")
        self._tarea("PRENDER LAS LUCES DE AFUERA", "19:30")  # de la Tarde: va en el cierre que sigue

        cierre = self._cierre_de_toby()

        self.assertEqual(self._resumen(cierre["id"]), [
            ("2026-01-05", "07:00", "CONTAR EL CAMBIO", False),
            ("2026-01-05", "11:00", "REPONER LA HELADERA", False),
        ])

    def test_la_que_toca_despues_del_cierre_va_en_el_siguiente_y_no_se_repite(self):
        self._tarea("CONTAR EL CAMBIO", "07:00")
        self._tarea("PRENDER LAS LUCES DE AFUERA", "19:30")
        manana = self._cierre_de_toby()
        relevo_repo.abrir_caja(self.gabriela_id, 50000.0, _a_las(14, 5))

        tarde = turnos_repo.cerrar_turno(self.gabriela_id, ahora_dt=_a_las(22, 0))

        self.assertEqual([t["texto"] for t in self._tareas(manana["id"])], ["CONTAR EL CAMBIO"])
        self.assertEqual([t["texto"] for t in self._tareas(tarde["id"])], ["PRENDER LAS LUCES DE AFUERA"])

    def test_la_del_minuto_del_cierre_entra(self):
        self._tarea("CONTAR EL SOBRE", "14:00")

        cierre = self._cierre_de_toby(_a_las(14, 0))

        self.assertEqual([t["texto"] for t in self._tareas(cierre["id"])], ["CONTAR EL SOBRE"])

    def test_sin_tareas_la_lista_va_vacia_y_alla_no_va_el_campo(self):
        cierre = self._cierre_de_toby()

        self.assertEqual(self._tareas(cierre["id"]), [])
        self.assertNotIn("tareas", envio_pwa_repo.a_campos_firestore(self._datos(cierre["id"]))["fields"])

    def test_un_cierre_de_varios_dias_lleva_las_de_cada_dia_con_su_dia(self):
        tarea_id = self._tarea("PRENDER LAS LUCES DE AFUERA", "19:30")
        self._vender(self.admin_id, _a_las(9), 700.0)
        turnos_repo.cerrar_turno(self.admin_id, ahora_dt=_a_las(14, 0))
        tareas_turno_repo.marcar_hecha(self.gabriela_id, tarea_id, MARTES, ahora=_a_las(19, 40, MARTES))
        self._vender(self.admin_id, _a_las(9, dia=MIERCOLES), 700.0)

        cierre = turnos_repo.cerrar_turno(self.admin_id, ahora_dt=_a_las(14, 0, MIERCOLES))

        self.assertEqual(self._resumen(cierre["id"]), [
            ("2026-01-05", "19:30", "PRENDER LAS LUCES DE AFUERA", False),
            ("2026-01-06", "19:30", "PRENDER LAS LUCES DE AFUERA", True),
        ])


class TestComoVaCadaTarea(_ConTareas):
    def test_la_hecha_va_con_quien_y_a_que_hora_aunque_la_hayan_hecho_antes_de_su_hora(self):
        tarea_id = self._tarea("REPONER LA HELADERA", "11:00")
        tareas_turno_repo.marcar_hecha(self.toby_id, tarea_id, LUNES, ahora=_a_las(10, 20))

        cierre = self._cierre_de_toby()

        self.assertEqual(self._tareas(cierre["id"]), [{
            "dia": "2026-01-05", "hora": "11:00", "texto": "REPONER LA HELADERA", "hecha": True,
            "hechaPor": "TOBY", "hechaA": "10:20", "vecesPospuesta": 0, "pospusieron": [],
        }])

    def test_la_sin_hacer_va_con_quienes_la_pospusieron_y_cuantas_veces(self):
        tarea_id = self._tarea("SACAR LA BASURA", "11:00")
        tareas_turno_repo.posponer(self.toby_id, tarea_id, LUNES, 5, ahora=_a_las(11, 0))
        tareas_turno_repo.posponer(self.admin_id, tarea_id, LUNES, 10, ahora=_a_las(11, 6))
        tareas_turno_repo.posponer(self.toby_id, tarea_id, LUNES, 5, ahora=_a_las(11, 17))

        cierre = self._cierre_de_toby()

        self.assertEqual(self._tareas(cierre["id"]), [{
            "dia": "2026-01-05", "hora": "11:00", "texto": "SACAR LA BASURA", "hecha": False,
            "hechaPor": None, "hechaA": None, "vecesPospuesta": 3, "pospusieron": ["TOBY", "Dueño"],
        }])

    def test_viajan_como_lista_de_mapas_de_firestore(self):
        tarea_id = self._tarea("SACAR LA BASURA", "11:00")
        tareas_turno_repo.posponer(self.toby_id, tarea_id, LUNES, 5, ahora=_a_las(11, 0))
        cierre = self._cierre_de_toby()

        campos = envio_pwa_repo.a_campos_firestore(self._datos(cierre["id"]))["fields"]

        tarea = campos["tareas"]["arrayValue"]["values"][0]["mapValue"]["fields"]
        self.assertEqual(tarea["texto"], {"stringValue": "SACAR LA BASURA"})
        self.assertEqual(tarea["hora"], {"stringValue": "11:00"})
        self.assertEqual(tarea["hecha"], {"booleanValue": False})
        self.assertEqual(tarea["hechaPor"], {"nullValue": None})
        self.assertEqual(tarea["vecesPospuesta"], {"integerValue": "1"})
        self.assertEqual(tarea["pospusieron"], {"arrayValue": {"values": [{"stringValue": "TOBY"}]}})
        json.dumps(campos)  # es lo que viaja


class TestQuedaComoEstabaAlCerrar(_ConTareas):
    def test_marcarla_o_posponerla_despues_del_cierre_no_lo_cambia(self):
        tarea_id = self._tarea("SACAR LA BASURA", "11:00")
        cierre = self._cierre_de_toby()

        tareas_turno_repo.posponer(self.gabriela_id, tarea_id, LUNES, 5, ahora=_a_las(14, 10))
        tareas_turno_repo.marcar_hecha(self.gabriela_id, tarea_id, LUNES, ahora=_a_las(14, 20))

        tarea = self._tareas(cierre["id"])[0]
        self.assertEqual((tarea["hecha"], tarea["hechaPor"], tarea["vecesPospuesta"]), (False, None, 0))

    def test_cambiarla_o_borrarla_despues_del_cierre_no_lo_cambia(self):
        basura = self._tarea("SACAR LA BASURA", "11:00")
        heladera = self._tarea("REPONER LA HELADERA", "12:00")
        cierre = self._cierre_de_toby()

        tareas_turno_repo.modificar_tarea(self.admin_id, basura, "SACAR LA BASURA Y BARRER", "11:30", TODOS,
                                          ahora=_a_las(15, 0))
        tareas_turno_repo.borrar_tarea(self.admin_id, heladera, ahora=_a_las(15, 5))

        self.assertEqual(self._resumen(cierre["id"]), [
            ("2026-01-05", "11:00", "SACAR LA BASURA", False),
            ("2026-01-05", "12:00", "REPONER LA HELADERA", False),
        ])

    def test_una_borrada_antes_del_cierre_no_va(self):
        basura = self._tarea("SACAR LA BASURA", "11:00")
        tareas_turno_repo.borrar_tarea(self.admin_id, basura, ahora=_a_las(10, 0))

        cierre = self._cierre_de_toby()

        self.assertEqual(self._tareas(cierre["id"]), [])

    def test_mandarlo_de_nuevo_dias_despues_manda_lo_mismo(self):
        tarea_id = self._tarea("SACAR LA BASURA", "11:00")
        cierre = self._cierre_de_toby()
        antes = self._tareas(cierre["id"])

        tareas_turno_repo.marcar_hecha(self.gabriela_id, tarea_id, LUNES, ahora=_a_las(14, 20))
        tareas_turno_repo.marcar_hecha(self.gabriela_id, tarea_id, MARTES, ahora=_a_las(11, 5, MARTES))

        self.assertEqual(self._tareas(cierre["id"]), antes)


class TestElCierreSigueIgual(_ConTareas):
    def test_con_tareas_el_resto_de_lo_que_viaja_no_cambia(self):
        cierre = self._cierre_de_toby()
        datos_sin = self._datos(cierre["id"])
        self._tarea("CONTAR EL CAMBIO", "07:00")  # cargada "el lunes a las 05:00": ahora el mismo cierre la tiene

        datos_con = self._datos(cierre["id"])

        self.assertEqual(len(datos_con["tareas"]), 1)

        self.assertEqual({k: v for k, v in datos_con.items() if k != "tareas"},
                         {k: v for k, v in datos_sin.items() if k != "tareas"})


if __name__ == "__main__":
    unittest.main()
