# ============================================================
# Cliente gRPC hacia el servicio Agenda.
#
# Aquí está el corazón de la integración: Reservas (REST) se
# comunica con Agenda (gRPC) para consultar y modificar cupos.
# Como todo es petición -> respuesta única, usamos el modo de
# invocación gRPC "Unary" (los 3 métodos del .proto).
#
# Si Agenda está caída o tarda demasiado, lanzamos
# AgendaNoDisponibleError, y la API responde 503 (ver app.py).
# ============================================================
import os

import grpc

# Stubs generados por protoc (el Dockerfile los genera al construir).
import agenda_pb2
import agenda_pb2_grpc

# A quién hablamos por gRPC (lo definen las variables de entorno de
# docker-compose.yml).
AGENDA_HOST = os.environ.get("AGENDA_HOST", "agenda")
AGENDA_PORT = os.environ.get("AGENDA_PORT", "50051")

# Tiempo máximo de espera por respuesta (en segundos).
TIMEOUT = 3


class AgendaNoDisponibleError(Exception):
    """Se lanza cuando Agenda no responde (servicio caído o lento)."""


def _crear_stub():
    """Crea el canal y el 'stub': el objeto que permite llamar a los
    métodos remotos como si fueran métodos locales.

    El host es el nombre del servicio Agenda en la red de Docker
    (docker-compose.yml): no hay una ruta local a la que apelar.
    """
    canal = grpc.insecure_channel(f"{AGENDA_HOST}:{AGENDA_PORT}")
    return agenda_pb2_grpc.AgendaServiceStub(canal)


def _invocar(operacion, *args):
    """Ejecuta una operación gRPC. Si la conexión falla, convierte el
    error en AgendaNoDisponibleError para simplificar el manejo en la API."""
    try:
        return operacion(*args, timeout=TIMEOUT)
    except grpc.RpcError as e:
        raise AgendaNoDisponibleError(
            f"Agenda no responde (código {e.code().name})") from e


def listar_bloques(id_veterinario=0, fecha=""):
    """Pide a Agenda la lista de bloques horarios y la devuelve como
    una lista de diccionarios (fácil de serializar a JSON)."""
    stub = _crear_stub()
    respuesta = _invocar(stub.ListarBloques, agenda_pb2.ListarBloquesRequest(
        id_veterinario=id_veterinario, fecha=fecha))
    return [
        {
            "id": b.id,
            "id_veterinario": b.id_veterinario,
            "nombre_veterinario": b.nombre_veterinario,
            "especialidad": b.especialidad,
            "fecha": b.fecha,
            "hora_inicio": b.hora_inicio,
            "hora_fin": b.hora_fin,
            "cupos_libres": b.cupos_libres,
        }
        for b in respuesta.bloques
    ]


def reservar_cupo(id_bloque):
    """Solicita a Agenda reservar un cupo. Devuelve exito/mensaje y,
    si hubo éxito, los datos del bloque (para el comprobante)."""
    stub = _crear_stub()
    respuesta = _invocar(stub.ReservarCupo,
                         agenda_pb2.ReservarCupoRequest(id_bloque=id_bloque))

    bloque = None
    if respuesta.bloque.id:  # el servidor nos mandó los datos del bloque
        b = respuesta.bloque
        bloque = {
            "id": b.id,
            "nombre_veterinario": b.nombre_veterinario,
            "especialidad": b.especialidad,
            "fecha": b.fecha,
            "hora_inicio": b.hora_inicio,
            "hora_fin": b.hora_fin,
            "cupos_libres": b.cupos_libres,
        }
    return {"exito": respuesta.exito, "mensaje": respuesta.mensaje,
            "bloque": bloque}


def liberar_cupo(id_bloque):
    """Solicita a Agenda liberar un cupo (se usa al cancelar una reserva)."""
    stub = _crear_stub()
    respuesta = _invocar(stub.LiberarCupo,
                         agenda_pb2.LiberarCupoRequest(id_bloque=id_bloque))
    return {"exito": respuesta.exito, "mensaje": respuesta.mensaje}