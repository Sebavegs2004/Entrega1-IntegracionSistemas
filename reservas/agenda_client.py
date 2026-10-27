# ============================================================
# Cliente gRPC hacia el servicio Agenda.
# ============================================================
import os
import grpc

import agenda_pb2
import agenda_pb2_grpc

AGENDA_HOST = os.environ.get("AGENDA_HOST", "agenda")
AGENDA_PORT = os.environ.get("AGENDA_PORT", "50051")
TIMEOUT = 3

# Canal y stub reutilizables (evita abrir una conexión TCP por cada petición)
_CANAL = grpc.insecure_channel(f"{AGENDA_HOST}:{AGENDA_PORT}")
_STUB = agenda_pb2_grpc.AgendaServiceStub(_CANAL)


class AgendaNoDisponibleError(Exception):
    """Se lanza cuando Agenda está caída o rechaza la conexión (503)."""


class AgendaTimeoutError(Exception):
    """Se lanza cuando Agenda excede el tiempo de espera; resultado incierto (504)."""


class BloqueNoEncontradoError(Exception):
    """Se lanza cuando el id_bloque no existe en Agenda (404)."""


class ReglaNegocioAgendaError(Exception):
    """Se lanza ante errores de negocio reportados por Agenda (409 o 422)."""

    def __init__(self, codigo_http, error, detalle):
        super().__init__(detalle)
        self.codigo_http = codigo_http
        self.error = error
        self.detalle = detalle


def _serializar_bloque(b):
    return {
        "id": b.id,
        "id_veterinario": b.id_veterinario,
        "nombre_veterinario": b.nombre_veterinario,
        "especialidad": b.especialidad,
        "fecha": b.fecha,
        "hora_inicio": b.hora_inicio,
        "hora_fin": b.hora_fin,
        "cupos_libres": b.cupos_libres,
    }


def _invocar(operacion, request_msg):
    """Ejecuta una operación gRPC y traduce los códigos canónicos."""
    try:
        return operacion(request_msg, timeout=TIMEOUT)
    except grpc.RpcError as e:
        code = e.code()
        detalle = e.details() or "Error en el servicio Agenda"

        if code == grpc.StatusCode.NOT_FOUND:
            raise BloqueNoEncontradoError(detalle) from e
        if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
            raise ReglaNegocioAgendaError(409, "SIN_CUPO", detalle) from e
        if code in (grpc.StatusCode.FAILED_PRECONDITION, grpc.StatusCode.INVALID_ARGUMENT):
            raise ReglaNegocioAgendaError(422, "REGLA_NEGOCIO", detalle) from e
        if code == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise AgendaTimeoutError(
                f"Agenda excedió el tiempo límite de {TIMEOUT}s") from e

        raise AgendaNoDisponibleError(
            f"Agenda no responde (código {code.name})") from e


def listar_bloques(id_veterinario=0, fecha=""):
    """Pide a Agenda la lista de bloques horarios."""
    respuesta = _invocar(_STUB.ListarBloques, agenda_pb2.ListarBloquesRequest(
        id_veterinario=id_veterinario, fecha=fecha))
    return [_serializar_bloque(b) for b in respuesta.bloques]


def obtener_bloque(id_bloque):
    """Pide a Agenda el detalle de un bloque horario y su veterinario."""
    bloque = _invocar(_STUB.ObtenerBloque,
                      agenda_pb2.ObtenerBloqueRequest(id_bloque=id_bloque))
    return _serializar_bloque(bloque)


def reservar_cupo(id_bloque):
    """Solicita a Agenda reservar un cupo. Si vence el timeout, intenta
    compensar liberando el cupo para no dejar cupos huérfanos."""
    try:
        respuesta = _invocar(_STUB.ReservarCupo,
                             agenda_pb2.ReservarCupoRequest(id_bloque=id_bloque))
    except AgendaTimeoutError:
        # Compensación ante timeout: si Agenda terminó procesando el descuento
        # después de los 3s, devolvemos el cupo para mantener la consistencia.
        try:
            _STUB.LiberarCupo(
                agenda_pb2.LiberarCupoRequest(id_bloque=id_bloque),
                timeout=TIMEOUT
            )
        except grpc.RpcError:
            pass
        raise

    bloque = _serializar_bloque(respuesta.bloque) if respuesta.bloque.id else None
    return {
        "exito": respuesta.exito,
        "mensaje": respuesta.mensaje,
        "bloque": bloque,
    }


def liberar_cupo(id_bloque):
    """Solicita a Agenda liberar un cupo (se usa al cancelar una reserva)."""
    respuesta = _invocar(_STUB.LiberarCupo,
                         agenda_pb2.LiberarCupoRequest(id_bloque=id_bloque))
    return {"exito": respuesta.exito, "mensaje": respuesta.mensaje}