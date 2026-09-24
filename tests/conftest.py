# ============================================================
# Soporte compartido de los tests de contrato.
# No es un archivo de tests: solo fixtures y helpers.
# ============================================================
import os

import jsonschema
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


@pytest.fixture(scope="session")
def api_base():
    return os.environ.get("API_BASE", "http://reservas:5000")


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


@pytest.fixture(scope="session")
def client(api_base, api_key):
    class Cliente:
        def __init__(self, base, key):
            self.base = base
            self.key = key

        def llamar(self, metodo, path, usar_key=True, **kwargs):
            headers = dict(kwargs.pop("headers", {}))
            if usar_key:
                headers["X-API-Key"] = self.key
            return requests.request(metodo, self.base + path,
                                    headers=headers, timeout=5, **kwargs)

    return Cliente(api_base, api_key)