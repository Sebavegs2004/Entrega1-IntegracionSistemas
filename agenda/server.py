# ============================================================
# Servicio Agenda (gRPC) — Clínica Veterinaria VidaAnimal
#
# Este servicio es la FUENTE DE VERDAD de veterinarios y bloques
# horarios. Es un servicio interno: no se expone al exterior
# (en docker-compose no tiene puertos públicos).
#
# Modo de invocación: gRPC Unary. Cada operación es "cliente manda
# un mensaje -> servidor responde un mensaje", sin streaming, que
# es lo más sencillo y suficiente para consultar/reservar cupos.
# ============================================================
import os
from concurrent import futures

import grpc

# Clases generadas por protoc desde contracts/agenda.proto
# (el Dockerfile las genera al construir la imagen).
import agenda_pb2
import agenda_pb2_grpc
from db import get_conn, inicializar

# Puerto interno de gRPC (lo define docker-compose.yml).
AGENDA_PORT = os.environ.get("AGENDA_PORT", "50051")


class AgendaServiceServicer(agenda_pb2_grpc.AgendaServiceServicer):
    """Implementa las operaciones definidas en agenda.proto.

    Son las mismas tres que consume el cliente de Reservas: listar
    bloques, reservar un cupo y liberarlo. No hay ninguna operación en el
    .proto que el cliente no use, ni al revés.
    """

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
            if request.id_veterinario != 0:   # filtro opcional por veterinario
                sql += " AND b.id_veterinario = ?"
                params.append(request.id_veterinario)
            if request.fecha:                 # filtro opcional por fecha
                sql += " AND b.fecha = ?"
                params.append(request.fecha)
            sql += " ORDER BY b.fecha, b.hora_inicio"

            filas = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        bloques = []
        for f in filas:
            bloques.append(agenda_pb2.BloqueHorario(
                id=f["id_bloque"],
                id_veterinario=f["id_veterinario"],
                nombre_veterinario=f["nombre_veterinario"],
                especialidad=f["especialidad"],
                fecha=f["fecha"],
                hora_inicio=f["hora_inicio"],
                hora_fin=f["hora_fin"],
                cupos_libres=f["cupos_libres"],
            ))
        return agenda_pb2.ListarBloquesResponse(bloques=bloques)

    # -----------------------------------------------
    # 2) Reservar un cupo (resta 1)
    # -----------------------------------------------
    def ReservarCupo(self, request, context):
        conn = get_conn()
        try:
            # UPDATE atómico: solo descuenta si todavía quedan cupos.
            # Si rowcount == 0, el bloque no existía o estaba lleno.
            cur = conn.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres - 1
                   WHERE id_bloque = ? AND cupos_libres > 0""",
                (request.id_bloque,),
            )
            if cur.rowcount == 0:
                conn.rollback()   # no hay nada que guardar
                return agenda_pb2.ReservarCupoResponse(
                    exito=False, mensaje="No quedan cupos en ese bloque")

            # Recuperamos los datos del bloque (con el veterinario) para
            # devolverlos en la respuesta y que Reservas guarde una copia.
            f = conn.execute(
                """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                   FROM bloques_horarios b
                   JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                   WHERE b.id_bloque = ?""",
                (request.id_bloque,),
            ).fetchone()
            conn.commit()   # confirmamos el cambio en la base
        finally:
            conn.close()

        return agenda_pb2.ReservarCupoResponse(
            exito=True,
            mensaje="Cupo reservado",
            bloque=agenda_pb2.BloqueHorario(
                id=f["id_bloque"],
                id_veterinario=f["id_veterinario"],
                nombre_veterinario=f["nombre_veterinario"],
                especialidad=f["especialidad"],
                fecha=f["fecha"],
                hora_inicio=f["hora_inicio"],
                hora_fin=f["hora_fin"],
                cupos_libres=f["cupos_libres"],
            ),
        )

    # -----------------------------------------------
    # 3) Liberar un cupo (suma 1) — al cancelar una reserva
    # -----------------------------------------------
    def LiberarCupo(self, request, context):
        conn = get_conn()
        try:
            # Solo suma si no supera el tope del bloque.
            cur = conn.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres + 1
                   WHERE id_bloque = ? AND cupos_libres < cupos_totales""",
                (request.id_bloque,),
            )
            if cur.rowcount == 0:
                conn.rollback()
                return agenda_pb2.LiberarCupoResponse(
                    exito=False, mensaje="No se pudo liberar el cupo")
            conn.commit()
        finally:
            conn.close()

        return agenda_pb2.LiberarCupoResponse(exito=True, mensaje="Cupo liberado")


def serve():
    """Levanta el servidor gRPC."""
    # Crea el archivo SQLite y sus tablas (solo si no existen).
    inicializar()

    # Ejecuta las peticiones en hasta 10 hilos en paralelo.
    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agenda_pb2_grpc.add_AgendaServiceServicer_to_server(
        AgendaServiceServicer(), servidor)

    puerto = AGENDA_PORT
    # Escucha en todas las interfaces, pero solo es accesible
    # dentro de la red de Docker (no hay "ports" hacia el host).
    servidor.add_insecure_port(f"[::]:{puerto}")
    servidor.start()
    print(f"AgendaService escuchando en el puerto {puerto}")
    servidor.wait_for_termination()


if __name__ == "__main__":
    serve()
