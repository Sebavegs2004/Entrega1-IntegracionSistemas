# ============================================================
# Servicio Agenda (gRPC) — Clínica Veterinaria VidaAnimal
#
# Este servicio es la FUENTE DE VERDAD de veterinarios y bloques
# horarios. Es un servicio interno: no se expone al exterior
# (en docker-compose no tiene puertos públicos).
# ============================================================
import os
from concurrent import futures
from datetime import date

import grpc

import agenda_pb2
import agenda_pb2_grpc
from db import get_conn, inicializar

AGENDA_PORT = os.environ.get("AGENDA_PORT", "50051")


def _fila_a_proto(f):
    return agenda_pb2.BloqueHorario(
        id=f["id_bloque"],
        id_veterinario=f["id_veterinario"],
        nombre_veterinario=f["nombre_veterinario"],
        especialidad=f["especialidad"],
        fecha=f["fecha"],
        hora_inicio=f["hora_inicio"],
        hora_fin=f["hora_fin"],
        cupos_libres=f["cupos_libres"],
    )


class AgendaServiceServicer(agenda_pb2_grpc.AgendaServiceServicer):
    """Implementa las operaciones definidas en agenda.proto."""

    # -----------------------------------------------
    # 1) Listar la agenda de bloques disponibles
    # -----------------------------------------------
    def ListarBloques(self, request, context):
        conn = get_conn()
        try:
            sql = """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                     FROM bloques_horarios b
                     JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                     WHERE 1 = 1"""
            params = []
            if request.id_veterinario != 0:
                sql += " AND b.id_veterinario = ?"
                params.append(request.id_veterinario)
            if request.fecha:
                sql += " AND b.fecha = ?"
                params.append(request.fecha)
            sql += " ORDER BY b.fecha, b.hora_inicio"

            filas = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        bloques = [_fila_a_proto(f) for f in filas]
        return agenda_pb2.ListarBloquesResponse(bloques=bloques)

    # -----------------------------------------------
    # 2) Consultar un veterinario y sus cupos en un bloque
    # -----------------------------------------------
    def ObtenerBloque(self, request, context):
        conn = get_conn()
        try:
            f = conn.execute(
                """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                   FROM bloques_horarios b
                   JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                   WHERE b.id_bloque = ?""",
                (request.id_bloque,),
            ).fetchone()
        finally:
            conn.close()

        if not f:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"El bloque horario {request.id_bloque} no existe"
            )
        return _fila_a_proto(f)

    # -----------------------------------------------
    # 3) Reservar un cupo (resta 1 de forma atómica)
    # -----------------------------------------------
    def ReservarCupo(self, request, context):
        hoy = date.today().isoformat()
        conn = get_conn()
        try:
            # 1) Verificar existencia y fecha antes de descontar
            actual = conn.execute(
                "SELECT fecha, cupos_libres FROM bloques_horarios WHERE id_bloque = ?",
                (request.id_bloque,),
            ).fetchone()

            if not actual:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"El bloque horario {request.id_bloque} no existe"
                )

            if actual["fecha"] < hoy:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "No se puede reservar en un bloque con fecha pasada"
                )

            # 2) UPDATE atómico: solo descuenta si todavía quedan cupos (> 0).
            cur = conn.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres - 1
                   WHERE id_bloque = ? AND cupos_libres > 0""",
                (request.id_bloque,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                context.abort(
                    grpc.StatusCode.RESOURCE_EXHAUSTED,
                    "El bloque ya no tiene cupos libres"
                )

            f = conn.execute(
                """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                   FROM bloques_horarios b
                   JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                   WHERE b.id_bloque = ?""",
                (request.id_bloque,),
            ).fetchone()
            conn.commit()
        finally:
            conn.close()

        return agenda_pb2.ReservarCupoResponse(
            exito=True,
            mensaje="Cupo reservado",
            bloque=_fila_a_proto(f),
        )

    # -----------------------------------------------
    # 4) Liberar un cupo (suma 1 hasta el tope)
    # -----------------------------------------------
    def LiberarCupo(self, request, context):
        conn = get_conn()
        try:
            existe = conn.execute(
                "SELECT id_bloque FROM bloques_horarios WHERE id_bloque = ?",
                (request.id_bloque,),
            ).fetchone()
            if not existe:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"El bloque horario {request.id_bloque} no existe"
                )

            cur = conn.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres + 1
                   WHERE id_bloque = ? AND cupos_libres < cupos_totales""",
                (request.id_bloque,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    "El bloque ya tiene todos sus cupos libres"
                )
            conn.commit()
        finally:
            conn.close()

        return agenda_pb2.LiberarCupoResponse(exito=True, mensaje="Cupo liberado")


def serve():
    """Levanta el servidor gRPC."""
    inicializar()

    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agenda_pb2_grpc.add_AgendaServiceServicer_to_server(
        AgendaServiceServicer(), servidor)

    puerto = AGENDA_PORT
    servidor.add_insecure_port(f"[::]:{puerto}")
    servidor.start()
    print(f"AgendaService escuchando en el puerto {puerto}")
    servidor.wait_for_termination()


if __name__ == "__main__":
    serve()