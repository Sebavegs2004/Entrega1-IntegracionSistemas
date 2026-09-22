import logging
from concurrent import futures

import grpc

import agenda_pb2
import agenda_pb2_grpc
from db import get_conn, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agenda")


class AgendaServiceServicer(agenda_pb2_grpc.AgendaServiceServicer):

    def ConsultarDisponibilidad(self, request, context):
        conn = get_conn()
        row = conn.execute(
            "SELECT cupos_disponibles FROM bloque_horario WHERE id = ?",
            (request.id_bloque,),
        ).fetchone()
        conn.close()

        if row is None:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Bloque no encontrado")
            return agenda_pb2.DisponibilidadResponse()

        return agenda_pb2.DisponibilidadResponse(
            id_bloque=request.id_bloque,
            cupos_disponibles=row["cupos_disponibles"],
            disponible=row["cupos_disponibles"] > 0,
        )

    def ListarBloques(self, request, context):
        conn = get_conn()
        query = """
            SELECT b.*, v.nombre AS nombre_veterinario
            FROM bloque_horario b
            JOIN veterinario v ON v.id = b.id_veterinario
            WHERE 1=1
        """
        params = []
        if request.id_veterinario:
            query += " AND b.id_veterinario = ?"
            params.append(request.id_veterinario)
        if request.fecha:
            query += " AND b.fecha = ?"
            params.append(request.fecha)

        rows = conn.execute(query, params).fetchall()
        conn.close()

        bloques = [
            agenda_pb2.BloqueHorario(
                id=r["id"],
                id_veterinario=r["id_veterinario"],
                nombre_veterinario=r["nombre_veterinario"],
                fecha=r["fecha"],
                hora_inicio=r["hora_inicio"],
                hora_fin=r["hora_fin"],
                cupos_disponibles=r["cupos_disponibles"],
            )
            for r in rows
        ]
        return agenda_pb2.ListarBloquesResponse(bloques=bloques)

    def ReservarCupo(self, request, context):
        conn = get_conn()
        try:
            cur = conn.execute(
                """UPDATE bloque_horario
                   SET cupos_disponibles = cupos_disponibles - 1
                   WHERE id = ? AND cupos_disponibles > 0""",
                (request.id_bloque,),
            )
            conn.commit()
            if cur.rowcount == 0:
                return agenda_pb2.ReservarCupoResponse(
                    exito=False, mensaje="Sin cupos disponibles para ese bloque"
                )
            return agenda_pb2.ReservarCupoResponse(exito=True, mensaje="Cupo reservado")
        finally:
            conn.close()

    def LiberarCupo(self, request, context):
        conn = get_conn()
        try:
            cur = conn.execute(
                """UPDATE bloque_horario
                   SET cupos_disponibles = cupos_disponibles + 1
                   WHERE id = ? AND cupos_disponibles < cupos_totales""",
                (request.id_bloque,),
            )
            conn.commit()
            if cur.rowcount == 0:
                return agenda_pb2.LiberarCupoResponse(
                    exito=False, mensaje="No se pudo liberar el cupo (bloque inexistente o ya al tope)"
                )
            return agenda_pb2.LiberarCupoResponse(exito=True, mensaje="Cupo liberado")
        finally:
            conn.close()


def serve():
    init_db()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agenda_pb2_grpc.add_AgendaServiceServicer_to_server(AgendaServiceServicer(), server)
    port = "50051"
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"AgendaService escuchando en puerto {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
