# ============================================================
# Soporte compartido de los tests de contrato.
# No es un archivo de tests: solo fixtures y helpers.
# ============================================================
import os

import jsonschema
import mysql.connector
import pytest
import requests
import yaml
from jsonschema import Draft7Validator, FormatChecker

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENAPI = os.path.join(REPO_ROOT, "contracts", "openapi.yaml")


def _normalizar_nullable(nodo):
    """Convierte 'nullable: true' (sintaxis OpenAPI 3.0) a un union type
    JSON Schema, porque jsonschema no entiende la clave 'nullable'."""
    if isinstance(nodo, dict):
        nuevo = {}
        for k, v in nodo.items():
            if k == "nullable":
                tipo = nodo.get("type")
                if tipo:
                    nuevo["type"] = [tipo, "null"]
                continue
            nuevo[k] = _normalizar_nullable(v)
        return nuevo
    if isinstance(nodo, list):
        return [_normalizar_nullable(x) for x in nodo]
    return nodo


def validar_spec_openapi(spec):
    """Valida que contracts/openapi.yaml es un OpenAPI 3.0 bien formado.
    Version-robusta ante los cambios de API de openapi-spec-validator."""
    try:
        from openapi_spec_validator import validate
    except ImportError:  # openapi-spec-validator >= 0.7
        from openapi_spec_validator import OpenAPIV3SpecValidator

        def validate(s):
            OpenAPIV3SpecValidator(s).validate()
    validate(spec)


def validar_contra_schema(instancia, schema, spec):
    """Valida un cuerpo JSON real contra un schema de la spec.
    Resuelve los $ref internos y activa el chequeo de 'format: date'."""
    resolver = jsonschema.RefResolver(base_uri="", referrer=spec)
    validator = Draft7Validator(schema, resolver=resolver,
                                format_checker=FormatChecker())
    validator.validate(instancia)


def obtener_schema(spec, path, metodo, status):
    """Devuelve el schema JSON de una respuesta documentada en la spec."""
    return (spec["paths"][path][metodo]["responses"][status]
            ["content"]["application/json"]["schema"])


def _conexion_db():
    """Abre una conexión a la base de Reservas (misma config que el servicio)."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "mysql_reservas"),
        user=os.environ.get("DB_USER", "reservas"),
        password=os.environ.get("DB_PASSWORD", "reservas123"),
        database=os.environ.get("DB_NAME", "reservas_db"),
    )


@pytest.fixture(scope="session")
def api_base():
    return os.environ.get("API_BASE", "http://reservas:5000")


@pytest.fixture(scope="session")
def api_base_degradada():
    return os.environ.get("DEGRADADA_BASE", "http://reservas-degradada:5000")


@pytest.fixture(scope="session")
def api_key():
    return os.environ.get("API_KEY", "clave-secreta-vet-2026")


@pytest.fixture(scope="session")
def spec_yaml():
    """La spec tal como está en el repo (sin normalizar)."""
    with open(OPENAPI) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def spec(spec_yaml):
    """La spec con 'nullable' normalizado a union type (para jsonschema)."""
    return _normalizar_nullable(spec_yaml)


class Cliente:
    """Cliente HTTP mínimo: inyecta X-API-Key en cada llamada y
    no levanta excepciones (los tests deciden con los status code)."""

    def __init__(self, base, key):
        self.base = base
        self.key = key

    def llamar(self, metodo, path, usar_key=True, **kwargs):
        headers = dict(kwargs.pop("headers", {}))
        if usar_key:
            headers["X-API-Key"] = self.key
        return requests.request(metodo, self.base + path,
                                headers=headers, timeout=5, **kwargs)


@pytest.fixture(scope="session")
def client(api_base, api_key):
    return Cliente(api_base, api_key)


@pytest.fixture(scope="session")
def client_degradada(api_base_degradada, api_key):
    """Cliente contra la instancia reservas-degradada (Agenda caída)."""
    return Cliente(api_base_degradada, api_key)


@pytest.fixture(scope="session")
def crea(client):
    """Crea dueños/reservas por la API y registra sus ids para borrarlos
    por MySQL al final de la sesión. La API no expone DELETE de dueños
    ni borrado físico de reservas, así que la limpieza va por SQL directo."""

    class Registro:
        def __init__(self):
            self.ids_duenos = []
            self.ids_reservas = []

        def dueno(self, json):
            r = client.llamar("POST", "/v1/duenos", json=json)
            assert r.status_code == 201, r.text
            self.ids_duenos.append(r.json()["id_dueno"])
            return r

        def reserva(self, json):
            r = client.llamar("POST", "/v1/reservas", json=json)
            if r.status_code == 201:
                self.ids_reservas.append(r.json()["id_reserva"])
            return r  # sea 201/400/404/409, el test asertúa lo suyo

    registro = Registro()
    yield registro

    # ----- Teardown: corre siempre, aunque un test falle -----
    # Orden por FK: reservas antes que duenos.
    if not (registro.ids_duenos or registro.ids_reservas):
        return
    conn = None
    try:
        conn = _conexion_db()
        cur = conn.cursor()
        if registro.ids_reservas:
            fmt = ",".join(["%s"] * len(registro.ids_reservas))
            cur.execute(f"DELETE FROM reservas WHERE id_reserva IN ({fmt})",
                        registro.ids_reservas)
        if registro.ids_duenos:
            fmt = ",".join(["%s"] * len(registro.ids_duenos))
            cur.execute(f"DELETE FROM reservas WHERE id_dueno IN ({fmt})",
                        registro.ids_duenos)  # barre huérfanas por FK
            cur.execute(f"DELETE FROM duenos WHERE id_dueno IN ({fmt})",
                        registro.ids_duenos)
        conn.commit()
    except Exception as e:
        print(f"[limpieza] AVISO: no se pudieron limpiar los datos "
              f"de esta corrida ({e!r})")
    finally:
        if conn:
            conn.close()