# ============================================================
# Pruebas de CONTRATO gRPC: el servicio Agenda implementa
# fielmente contracts/agenda.proto.
#   - El .proto compila y su descriptor expone los 4 RPC.
#   - Los 4 métodos responden como dicta el contrato.
#
# OJO: este archivo debe correr DENTRO de la red de Docker
# (agenda:50051) porque el servicio Agenda no publica puertos
# al host. Lo normal es vía el servicio "tests" del compose.
# ============================================================
import os
import subprocess
import sys
import tempfile

import grpc
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTO_DIR = os.path.join(REPO, "contracts")
PROTO_FILE = os.path.join(PROTO_DIR, "agenda.proto")

METODOS = ["ConsultarVeterinario", "ListarBloques", "ReservarCupo", "LiberarCupo"]


@pytest.fixture(scope="module")
def pb2():
    """Compila agenda.proto a un directorio temporal y expone los stubs.
    Así los tests usan siempre código generado del contrato actual."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["python", "-m", "grpc_tools.protoc",
             "-I", PROTO_DIR, "--python_out=.", "--grpc_python_out=.",
             PROTO_FILE],
            capture_output=True, text=True, cwd=tmp)
        assert proc.returncode == 0, proc.stderr or proc.stdout
        sys.path.insert(0, tmp)
        try:
            import agenda_pb2
            import agenda_pb2_grpc
            yield agenda_pb2, agenda_pb2_grpc
        finally:
            sys.path.remove(tmp)


@pytest.fixture(scope="module")
def stub(pb2):
    _, mod = pb2
    host = os.environ.get("AGENDA_HOST", "agenda")
    puerto = os.environ.get("AGENDA_PORT", "50051")
    canal = grpc.insecure_channel(f"{host}:{puerto}")
    return mod.AgendaServiceStub(canal)


# ------------------------------------------------------------
# 1) El contrato (proto) es válido y completo
# ------------------------------------------------------------
def test_proto_compila_y_descriptor_con_4_rpc(pb2):
    agenda_pb2, _ = pb2
    servicio = agenda_pb2.DESCRIPTOR.services_by_name["AgendaService"]
    metodos = sorted(m.name for m in servicio.methods)
    assert metodos == sorted(METODOS)


# ------------------------------------------------------------
# 2) ListarBloques
# ------------------------------------------------------------
def test_listar_bloques_sin_filtros(stub, pb2):
    req, _ = pb2
    r = stub.ListarBloques(req.ListarBloquesRequest(), timeout=5)
    assert len(r.bloques) > 0
    for b in r.bloques:
        assert b.id > 0
        assert b.id_veterinario > 0
        assert b.nombre_veterinario
        assert b.especialidad
        assert b.fecha            # "YYYY-MM-DD"
        assert b.hora_inicio and b.hora_fin   # "HH:MM"
        assert b.cupos_libres >= 0


def test_listar_bloques_por_veterinario(stub, pb2):
    req, _ = pb2
    r = stub.ListarBloques(req.ListarBloquesRequest(id_veterinario=1), timeout=5)
    assert len(r.bloques) > 0
    assert all(b.id_veterinario == 1 for b in r.bloques)


def test_listar_bloques_por_fecha(stub, pb2):
    req, _ = pb2
    r = stub.ListarBloques(req.ListarBloquesRequest(fecha="2026-09-24"), timeout=5)
    assert len(r.bloques) > 0
    assert all(b.fecha == "2026-09-24" for b in r.bloques)


# ------------------------------------------------------------
# 3) ConsultarVeterinario
# ------------------------------------------------------------
def test_consultar_veterinario_ok(stub, pb2):
    req, _ = pb2
    r = stub.ConsultarVeterinario(
        req.ConsultarVeterinarioRequest(id_veterinario=1, id_bloque=1), timeout=5)
    assert r.nombre == "Dra. Carmen Rojas"   # dato del seed
    assert r.especialidad
    assert r.id_veterinario == 1 and r.id_bloque == 1
    assert r.disponible == (r.cupos_libres > 0)


def test_consultar_veterinario_no_encontrado(stub, pb2):
    req, _ = pb2
    with pytest.raises(grpc.RpcError) as exc:
        stub.ConsultarVeterinario(
            req.ConsultarVeterinarioRequest(id_veterinario=99999, id_bloque=1),
            timeout=5)
    assert exc.value.code() == grpc.StatusCode.NOT_FOUND


# ------------------------------------------------------------
# 4) ReservarCupo / LiberarCupo
# ------------------------------------------------------------
def test_reservar_y_liberar_cupo(stub, pb2):
    req, _ = pb2
    bloque = next(b for b in stub.ListarBloques(
        req.ListarBloquesRequest(), timeout=5).bloques if b.cupos_libres > 0)

    r = stub.ReservarCupo(req.ReservarCupoRequest(id_bloque=bloque.id), timeout=5)
    assert r.exito is True
    assert r.bloque.id == bloque.id
    assert r.bloque.cupos_libres == bloque.cupos_libres - 1

    # Liberamos para dejar la base como estaba (suite re-ejecutable).
    l = stub.LiberarCupo(req.LiberarCupoRequest(id_bloque=bloque.id), timeout=5)
    assert l.exito is True


def test_reservar_cupo_sin_cupos(stub, pb2):
    req, _ = pb2
    # En el seed, el bloque 3 está agotado (cupos_libres = 0).
    r = stub.ReservarCupo(req.ReservarCupoRequest(id_bloque=3), timeout=5)
    assert r.exito is False


def test_liberar_no_excede_tope(stub, pb2):
    req, _ = pb2
    # En el seed, el bloque 1 está lleno (3/3): liberar no debe sumar más.
    r = stub.LiberarCupo(req.LiberarCupoRequest(id_bloque=1), timeout=5)
    assert r.exito is False