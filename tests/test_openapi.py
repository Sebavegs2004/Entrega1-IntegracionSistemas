# ============================================================
# Pruebas de CONTRATO REST: la implementación (API Reservas)
# cumple contracts/openapi.yaml.
#   - La spec es un OpenAPI 3.0 válido.
#   - Cada endpoint documentado existe en la API viva.
#   - Cada cuerpo de respuesta (éxitos y errores) valida contra
#     el schema declarado en la spec.
#   - Flujo end-to-end: crear dueño -> reservar -> cancelar con
#     verificación de que los cupos de Agenda suben/bajan.
#
# Ejecución: requiere la pila arriba. Por defecto apunta a
#   http://reservas:5000 (red Docker). Desde el host se puede
#   sobreescribir con API_BASE=http://localhost:5000.
# ============================================================
import pytest

from conftest import obtener_schema, validar_contra_schema, validar_spec_openapi


@pytest.fixture(scope="session")
def session_dueno(client):
    """Un dueño creado en la base de Reservas, reutilizable en el suite."""
    r = client.llamar("POST", "/v1/duenos", json={
        "nombre": "Dueño de pruebas",
        "telefono": "+56900000001",
    })
    assert r.status_code == 201
    return r.json()["id_dueno"]


# ------------------------------------------------------------
# 1) La spec es válida y /v1/health está documentado
# ------------------------------------------------------------
def test_spec_openapi_es_valida(spec_yaml):
    validar_spec_openapi(spec_yaml)


def test_health_documentado_y_publico(spec, client):
    assert "/v1/health" in spec["paths"]
    operacion = spec["paths"]["/v1/health"]["get"]
    assert operacion.get("security") == []   # no exige API Key

    r = client.llamar("GET", "/v1/health", usar_key=False)
    assert r.status_code == 200
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/health", "get", "200"), spec)


# ------------------------------------------------------------
# 2) Cobertura: todo lo documentado existe en la API viva
# ------------------------------------------------------------
def test_cobertura_documentado_vs_implementacion(client, spec):
    for path, item in spec["paths"].items():
        camino = path.replace("{id}", "1")
        for metodo in ("get", "post", "delete"):
            if metodo not in item:
                continue
            # Sin API Key, una ruta existente responde 401 (o 200 en health),
            # mientras que una ruta inexistente responde 404.
            r = client.llamar(metodo.upper(), camino, usar_key=False)
            assert r.status_code != 404, (
                f"{metodo.upper()} {path} no existe en la implementación")


def test_ui_disponible(client):
    for path in ("/", "/swagger", "/openapi.yaml"):
        assert client.llamar("GET", path, usar_key=False).status_code == 200


# ------------------------------------------------------------
# 3) Cuerpos de error contra sus schemas
# ------------------------------------------------------------
def test_401_sin_api_key(client, spec):
    r = client.llamar("GET", "/v1/duenos", usar_key=False)
    assert r.status_code == 401
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos", "get", "401"), spec)


def test_401_api_key_invalida(client, spec):
    r = client.llamar("GET", "/v1/duenos", usar_key=False,
                      headers={"X-API-Key": "clave-incorrecta"})
    assert r.status_code == 401
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos", "get", "401"), spec)


def test_crear_dueno_400(client, spec):
    r = client.llamar("POST", "/v1/duenos", json={"telefono": "+56"})
    assert r.status_code == 400
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos", "post", "400"), spec)


def test_obtener_dueno_404(client, spec):
    r = client.llamar("GET", "/v1/duenos/99999999")
    assert r.status_code == 404
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos/{id}", "get", "404"), spec)


def test_crear_reserva_400(client, spec):
    r = client.llamar("POST", "/v1/reservas", json={})
    assert r.status_code == 400
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas", "post", "400"), spec)


def test_crear_reserva_dueno_inexistente_404(client, spec):
    r = client.llamar("POST", "/v1/reservas", json={
        "id_dueno": 99999999, "id_bloque": 1, "mascota_nombre": "Rex"})
    assert r.status_code == 404
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas", "post", "404"), spec)


def test_crear_reserva_sin_cupo_409(client, spec, session_dueno):
    # En el seed de Agenda, el bloque 3 está agotado (cupos_libres = 0).
    r = client.llamar("POST", "/v1/reservas", json={
        "id_dueno": session_dueno, "id_bloque": 3, "mascota_nombre": "Rex"})
    assert r.status_code == 409
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas", "post", "409"), spec)


def test_obtener_reserva_404(client, spec):
    r = client.llamar("GET", "/v1/reservas/99999999")
    assert r.status_code == 404
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas/{id}", "get", "404"), spec)


def test_cancelar_reserva_404(client, spec):
    r = client.llamar("DELETE", "/v1/reservas/99999999")
    assert r.status_code == 404
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas/{id}", "delete", "404"), spec)


# ------------------------------------------------------------
# 4) Cuerpos de éxito contra sus schemas
# ------------------------------------------------------------
def test_crear_dueno_201(client, spec):
    r = client.llamar("POST", "/v1/duenos", json={
        "nombre": "Juan Pérez", "telefono": "+56911112222", "email": None})
    assert r.status_code == 201
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos", "post", "201"), spec)


def test_listar_duenos_200(client, spec):
    r = client.llamar("GET", "/v1/duenos")
    assert r.status_code == 200
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos", "get", "200"), spec)


def test_obtener_dueno_200(client, spec, session_dueno):
    r = client.llamar("GET", f"/v1/duenos/{session_dueno}")
    assert r.status_code == 200
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/duenos/{id}", "get", "200"), spec)


def test_listar_bloques_200(client, spec):
    r = client.llamar("GET", "/v1/bloques")
    assert r.status_code == 200
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/bloques", "get", "200"), spec)
    assert len(r.json()) > 0   # los bloques vienen de Agenda vía gRPC


def test_listar_reservas_200(client, spec):
    r = client.llamar("GET", "/v1/reservas")
    assert r.status_code == 200
    validar_contra_schema(
        r.json(), obtener_schema(spec, "/v1/reservas", "get", "200"), spec)


# ------------------------------------------------------------
# 5) Flujo end-to-end con verificación del cupo en Agenda
# ------------------------------------------------------------
def test_flujo_reservar_listar_cancelar(client, spec, session_dueno):
    bloques = client.llamar("GET", "/v1/bloques").json()
    bloque = next(b for b in bloques if b["cupos_libres"] > 0)
    cupo_antes = bloque["cupos_libres"]

    # Crear la reserva
    r = client.llamar("POST", "/v1/reservas", json={
        "id_dueno": session_dueno,
        "id_bloque": bloque["id"],
        "mascota_nombre": "Rex",
        "motivo": "Control anual",
    })
    assert r.status_code == 201
    reserva = r.json()
    validar_contra_schema(
        reserva, obtener_schema(spec, "/v1/reservas", "post", "201"), spec)

    # El cupo del bloque bajó 1 (lo descuenta Agenda vía gRPC)
    bloques2 = client.llamar("GET", "/v1/bloques").json()
    b2 = next(b for b in bloques2 if b["id"] == bloque["id"])
    assert b2["cupos_libres"] == cupo_antes - 1

    # La reserva aparece en el listado y se puede consultar por id
    rl = client.llamar("GET", "/v1/reservas")
    assert rl.status_code == 200
    ids = [x["id_reserva"] for x in rl.json()]
    assert reserva["id_reserva"] in ids

    r1 = client.llamar("GET", f"/v1/reservas/{reserva['id_reserva']}")
    assert r1.status_code == 200
    validar_contra_schema(
        r1.json(), obtener_schema(spec, "/v1/reservas/{id}", "get", "200"), spec)

    # Cancelar (204 sin cuerpo)
    rc = client.llamar("DELETE", f"/v1/reservas/{reserva['id_reserva']}")
    assert rc.status_code == 204
    assert rc.text == ""

    # El cupo volvió a su valor original (se libera en Agenda)
    bloques3 = client.llamar("GET", "/v1/bloques").json()
    b3 = next(b for b in bloques3 if b["id"] == bloque["id"])
    assert b3["cupos_libres"] == cupo_antes

    # Cancelar dos veces la misma reserva -> 409 YA_CANCELADA
    rc2 = client.llamar("DELETE", f"/v1/reservas/{reserva['id_reserva']}")
    assert rc2.status_code == 409
    validar_contra_schema(
        rc2.json(), obtener_schema(spec, "/v1/reservas/{id}", "delete", "409"), spec)