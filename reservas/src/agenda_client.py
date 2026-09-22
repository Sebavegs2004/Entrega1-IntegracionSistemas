import os
import grpc

import agenda_pb2
import agenda_pb2_grpc

AGENDA_HOST = os.environ.get("AGENDA_HOST", "localhost")
AGENDA_PORT = os.environ.get("AGENDA_PORT", "50051")
TIMEOUT_SEGUNDOS = float(os.environ.get("AGENDA_TIMEOUT", "2"))


class AgendaNoDisponibleError(Exception):
    """Se lanza cuando el servicio Agenda no responde a tiempo (T7)."""
    pass


def _get_stub():
    channel = grpc.insecure_channel(f"{AGENDA_HOST}:{AGENDA_PORT}")
    return agenda_pb2_grpc.AgendaServiceStub(channel)


def reservar_cupo(id_bloque: str):
    stub = _get_stub()
    try:
        resp = stub.ReservarCupo(
            agenda_pb2.ReservarCupoRequest(id_bloque=id_bloque), timeout=TIMEOUT_SEGUNDOS
        )
        return {"exito": resp.exito, "mensaje": resp.mensaje}
    except grpc.RpcError as e:
        raise AgendaNoDisponibleError(str(e))


def liberar_cupo(id_bloque: str):
    stub = _get_stub()
    try:
        resp = stub.LiberarCupo(
            agenda_pb2.LiberarCupoRequest(id_bloque=id_bloque), timeout=TIMEOUT_SEGUNDOS
        )
        return {"exito": resp.exito, "mensaje": resp.mensaje}
    except grpc.RpcError as e:
        raise AgendaNoDisponibleError(str(e))


def consultar_disponibilidad(id_bloque: str):
    stub = _get_stub()
    try:
        resp = stub.ConsultarDisponibilidad(
            agenda_pb2.ConsultarDisponibilidadRequest(id_bloque=id_bloque),
            timeout=TIMEOUT_SEGUNDOS,
        )
        return {
            "id_bloque": resp.id_bloque,
            "cupos_disponibles": resp.cupos_disponibles,
            "disponible": resp.disponible,
        }
    except grpc.RpcError as e:
        raise AgendaNoDisponibleError(str(e))


def listar_bloques(id_veterinario: str = "", fecha: str = ""):
    stub = _get_stub()
    try:
        resp = stub.ListarBloques(
            agenda_pb2.ListarBloquesRequest(id_veterinario=id_veterinario, fecha=fecha),
            timeout=TIMEOUT_SEGUNDOS,
        )
        return [
            {
                "id": b.id,
                "id_veterinario": b.id_veterinario,
                "nombre_veterinario": b.nombre_veterinario,
                "fecha": b.fecha,
                "hora_inicio": b.hora_inicio,
                "hora_fin": b.hora_fin,
                "cupos_disponibles": b.cupos_disponibles,
            }
            for b in resp.bloques
        ]
    except grpc.RpcError as e:
        raise AgendaNoDisponibleError(str(e))
