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
from db import get_conn, get_dict_cursor


class AgendaServiceServicer(agenda_pb2_grpc.AgendaServiceServicer):
    """Implementa las operaciones definidas en agenda.proto."""

    # -----------------------------------------------
    # 1) Consultar un veterinario y sus cupos libres
    # -----------------------------------------------
    def ConsultarVeterinario(self, request, context):
        conn = get_conn()
        try:
            cur = get_dict_cursor(conn)
            # JOIN: juntamos la fila del veterinario con su bloque
            # usando el id del bloque que llegó en el request.
            cur.execute(
                """SELECT v.nombre, v.especialidad, b.cupos_libres
                   FROM veterinarios v
                   JOIN bloques_horarios b
                     ON b.id_veterinario = v.id_veterinario
                   WHERE v.id_veterinario = %s AND b.id_bloque = %s""",
                (request.id_veterinario, request.id_bloque),
            )
            fila = cur.fetchone()
        finally:
            conn.close()

        if fila is None:
            # Error gRPC: el canal le avisa al cliente con un código.
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("Veterinario o bloque no encontrado")
            return agenda_pb2.VeterinarioResponse()

        return agenda_pb2.VeterinarioResponse(
            id_veterinario=request.id_veterinario,
            nombre=fila["nombre"],
            especialidad=fila["especialidad"],
            id_bloque=request.id_bloque,
            cupos_libres=fila["cupos_libres"],
            disponible=fila["cupos_libres"] > 0,
        )

    # -----------------------------------------------
    # 2) Listar la agenda de bloques disponibles
    # -----------------------------------------------
    def ListarBloques(self, request, context):
        conn = get_conn()
        try:
            cur = get_dict_cursor(conn)
            sql = """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                     FROM bloques_horarios b
                     JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                     WHERE 1 = 1"""
            params = []
            if request.id_veterinario != 0:   # filtro opcional por veterinario
                sql += " AND b.id_veterinario = %s"
                params.append(request.id_veterinario)
            if request.fecha:                 # filtro opcional por fecha
                sql += " AND b.fecha = %s"
                params.append(request.fecha)
            sql += " ORDER BY b.fecha, b.hora_inicio"

            cur.execute(sql, params)
            filas = cur.fetchall()
        finally:
            conn.close()

        bloques = []
        for f in filas:
            # str(fecha) convierte la fecha (DATE) en texto "AAAA-MM-DD"
            bloques.append(agenda_pb2.BloqueHorario(
                id=f["id_bloque"],
                id_veterinario=f["id_veterinario"],
                nombre_veterinario=f["nombre_veterinario"],
                especialidad=f["especialidad"],
                fecha=str(f["fecha"]),
                hora_inicio=f["hora_inicio"],
                hora_fin=f["hora_fin"],
                cupos_libres=f["cupos_libres"],
            ))
        return agenda_pb2.ListarBloquesResponse(bloques=bloques)

    # -----------------------------------------------
    # 3) Reservar un cupo (resta 1)
    # -----------------------------------------------
    def ReservarCupo(self, request, context):
        conn = get_conn()
        try:
            cur = get_dict_cursor(conn)
            # UPDATE atómico: solo descuenta si todavía quedan cupos.
            # Si rowcount == 0, el bloque no existía o estaba lleno.
            cur.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres - 1
                   WHERE id_bloque = %s AND cupos_libres > 0""",
                (request.id_bloque,),
            )
            if cur.rowcount == 0:
                conn.rollback()   # no hay nada que guardar
                return agenda_pb2.ReservarCupoResponse(
                    exito=False, mensaje="No quedan cupos en ese bloque")

            # Recuperamos los datos del bloque (con el veterinario) para
            # devolverlos en la respuesta y que Reservas guarde una copia.
            cur.execute(
                """SELECT b.*, v.nombre AS nombre_veterinario, v.especialidad
                   FROM bloques_horarios b
                   JOIN veterinarios v ON v.id_veterinario = b.id_veterinario
                   WHERE b.id_bloque = %s""",
                (request.id_bloque,),
            )
            f = cur.fetchone()
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
                fecha=str(f["fecha"]),
                hora_inicio=f["hora_inicio"],
                hora_fin=f["hora_fin"],
                cupos_libres=f["cupos_libres"],
            ),
        )

    # -----------------------------------------------
    # 4) Liberar un cupo (suma 1) — al cancelar una reserva
    # -----------------------------------------------
    def LiberarCupo(self, request, context):
        conn = get_conn()
        try:
            cur = get_dict_cursor(conn)
            # Solo suma si no supera el tope del bloque.
            cur.execute(
                """UPDATE bloques_horarios
                   SET cupos_libres = cupos_libres + 1
                   WHERE id_bloque = %s AND cupos_libres < cupos_totales""",
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
    # Ejecuta las peticiones en hasta 10 hilos en paralelo.
    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agenda_pb2_grpc.add_AgendaServiceServicer_to_server(
        AgendaServiceServicer(), servidor)

    puerto = os.environ.get("AGENDA_PORT", "50051")
    # Escucha en todas las interfaces, pero solo es accesible
    # dentro de la red de Docker (no hay "ports" hacia el host).
    servidor.add_insecure_port(f"[::]:{puerto}")
    servidor.start()
    print(f"AgendaService escuchando en el puerto {puerto}")
    servidor.wait_for_termination()


if __name__ == "__main__":
    serve()