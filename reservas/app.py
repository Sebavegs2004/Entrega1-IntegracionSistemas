# ============================================================
# Servicio Reservas (Flask) — Clínica Veterinaria VidaAnimal
# ============================================================
import hashlib
import json
import os
from functools import wraps
from pathlib import Path

import redis
import yaml
from flask import Flask, abort, jsonify, render_template, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import agenda_client
from db import actualizar, consultar, ejecutar, inicializar

app = Flask(__name__)

# Configuración de claves por rol desde variables de entorno.
API_KEY_ESCRITURA = os.environ.get("API_KEY", "")
API_KEY_LECTURA = os.environ.get("API_KEY_LECTURA", "")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis_cache")

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    db=0,
    decode_responses=True
)

RUTA_CONTRATO = Path(app.root_path) / "contracts" / "openapi.yaml"
CABECERA_IDEMPOTENCIA = "Idempotency-Key"

CLAVE_BLOQUES = "cache:bloques"
TTL_BLOQUES = 60          # 1 minuto
TTL_IDEMPOTENCIA = 86400  # 24 horas

# Inicializa el esquema SQLite al cargar el módulo (compatible con Gunicorn)
inicializar()


# ============================================================
# Autenticación y Autorización con API Key por roles (401 y 403)
# ============================================================
def requiere_api_key(rol="lectura"):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            clave = request.headers.get("X-API-Key")
            if not clave:
                return jsonify({"error": "NO_AUTORIZADO",
                                "detalle": "Falta el header X-API-Key"}), 401

            claves_validas = {k for k in (API_KEY_ESCRITURA, API_KEY_LECTURA) if k}
            if clave not in claves_validas:
                return jsonify({"error": "NO_AUTORIZADO",
                                "detalle": "API Key inválida"}), 401

            if rol == "escritura" and clave != API_KEY_ESCRITURA:
                return jsonify({"error": "PROHIBIDO",
                                "detalle": "La API Key proporcionada solo tiene permisos de lectura"}), 403

            return f(*args, **kwargs)
        return envoltura
    return decorador


# ============================================================
# Validación de la entrada
# ============================================================
class DatosInvalidos(Exception):
    """El cuerpo de la petición no cumple el modelo esperado."""

    def __init__(self, detalle):
        super().__init__(detalle)
        self.detalle = detalle


class NuevoDueno(BaseModel):
    """Cuerpo de POST /v1/duenos."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nombre: str = Field(min_length=1)
    telefono: str = Field(min_length=1)
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class NuevaReserva(BaseModel):
    """Cuerpo de POST /v1/reservas."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id_dueno: int = Field(ge=1)
    id_bloque: int = Field(ge=1)
    mascota_nombre: str = Field(min_length=1)
    motivo: str | None = None


def cuerpo_json(modelo):
    """Devuelve el cuerpo de la petición ya validado con el modelo dado."""
    datos = request.get_json()
    if not isinstance(datos, dict):
        raise DatosInvalidos("El cuerpo JSON debe ser un objeto")
    try:
        return modelo.model_validate(datos)
    except ValidationError as e:
        campos = [n for n, f in modelo.model_fields.items() if f.is_required()]
        raise DatosInvalidos(
            f"Datos inválidos o mal formados. Revisa los campos: {', '.join(campos)} (y formato de email si aplica)") from e


# ============================================================
# Manejadores globales de errores HTTP
# ============================================================
@app.errorhandler(DatosInvalidos)
def datos_invalidos(e):
    return jsonify({"error": "DATOS_INVALIDOS",
                    "detalle": e.detalle}), 400


@app.errorhandler(agenda_client.BloqueNoEncontradoError)
def bloque_no_encontrado(e):
    return jsonify({"error": "NO_ENCONTRADO",
                    "detalle": str(e)}), 404


@app.errorhandler(agenda_client.ReglaNegocioAgendaError)
def regla_negocio_agenda(e):
    return jsonify({"error": e.error,
                    "detalle": e.detalle}), e.codigo_http


@app.errorhandler(400)
def peticion_malformada(e):
    return jsonify({"error": "DATOS_INVALIDOS",
                    "detalle": "La petición no es válida. Revisa los datos enviados."}), 400


@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"error": "NO_ENCONTRADO",
                    "detalle": "Recurso no encontrado"}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"error": "METODO_NO_PERMITIDO",
                    "detalle": "El método HTTP no está permitido para esta ruta."}), 405


@app.errorhandler(415)
def contenido_no_soportado(e):
    return jsonify({"error": "CONTENIDO_NO_SOPORTADO",
                    "detalle": "El cuerpo de la petición debe ser JSON (Content-Type: application/json)."}), 415


@app.errorhandler(500)
def error_interno(e):
    return jsonify({"error": "ERROR_INTERNO",
                    "detalle": "Ocurrió un error inesperado en el servidor."}), 500


@app.errorhandler(503)
def agenda_no_disponible(e):
    respuesta = jsonify({"error": "AGENDA_NO_DISPONIBLE",
                         "detalle": "El servicio de Agenda no está disponible. Intenta de nuevo en un momento."})
    respuesta.status_code = 503
    respuesta.headers["Retry-After"] = "5"
    return respuesta


@app.errorhandler(504)
def agenda_timeout(e):
    respuesta = jsonify({"error": "AGENDA_TIMEOUT",
                         "detalle": "El servicio de Agenda tardó demasiado en responder y la operación fue revertida por seguridad."})
    respuesta.status_code = 504
    respuesta.headers["Retry-After"] = "5"
    return respuesta


# ============================================================
# Redis (caché de bloques e idempotencia atómica)
# ============================================================
def leer_bloques_cacheados():
    try:
        guardado = redis_client.get(CLAVE_BLOQUES)
        return json.loads(guardado) if guardado else None
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al leer la caché: %s", e)
        return None


def guardar_bloques_cacheados(bloques):
    try:
        redis_client.setex(CLAVE_BLOQUES, TTL_BLOQUES, json.dumps(bloques))
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al guardar la caché: %s", e)


def olvidar_bloques():
    try:
        redis_client.delete(CLAVE_BLOQUES)
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al borrar la caché: %s", e)


def _hash_cuerpo(modelo_validado):
    canonico = json.dumps(modelo_validado.model_dump(), sort_keys=True)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def reclamar_clave_idempotencia(clave, body_hash):
    """Reserva la clave de idempotencia en Redis usando SET NX antes de hablar
    con Agenda. Evita que peticiones concurrentes con la misma clave creen
    reservas duplicadas y verifica que el cuerpo sea el mismo."""
    if not clave:
        return "NUEVA", None
    llave = f"idemp:reserva:{clave}"
    try:
        registro_inicial = json.dumps({"estado": "EN_PROCESO", "hash": body_hash})
        creado = redis_client.set(llave, registro_inicial, nx=True, ex=TTL_IDEMPOTENCIA)
        if creado:
            return "NUEVA", None

        raw = redis_client.get(llave)
        if not raw:
            return "NUEVA", None
        guardado = json.loads(raw)

        if guardado.get("hash") != body_hash:
            return "CUERPO_DISTINTO", None
        if guardado.get("estado") == "EN_PROCESO":
            return "EN_PROCESO", None
        return "COMPLETADA", guardado.get("reserva")
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al verificar idempotencia: %s", e)
        return "NUEVA", None


def confirmar_reserva_idempotente(clave, body_hash, reserva):
    """Guarda el resultado definitivo asociado a la clave y al hash del cuerpo."""
    if not clave:
        return
    try:
        registro = json.dumps({
            "estado": "COMPLETADA",
            "hash": body_hash,
            "reserva": reserva
        })
        redis_client.setex(f"idemp:reserva:{clave}", TTL_IDEMPOTENCIA, registro)
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al guardar la idempotencia: %s", e)


def liberar_clave_idempotencia(clave):
    """Elimina el bloqueo de la clave si la creación falló, para permitir reintentos."""
    if not clave:
        return
    try:
        redis_client.delete(f"idemp:reserva:{clave}")
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al liberar idempotencia: %s", e)


# ============================================================
# Interfaz web
# ============================================================
@app.get("/")
def index():
    return render_template("index.html")


@app.get("/v1/docs")
def docs():
    with open(RUTA_CONTRATO, encoding="utf-8") as archivo:
        contrato = yaml.safe_load(archivo)
    return render_template("swagger.html", contrato=contrato)


# ============================================================
# Dueños
# ============================================================
@app.post("/v1/duenos")
@requiere_api_key(rol="escritura")
def crear_dueno():
    datos = cuerpo_json(NuevoDueno)
    id_dueno = ejecutar(
        "INSERT INTO duenos (nombre, telefono, email) VALUES (?, ?, ?)",
        (datos.nombre, datos.telefono, datos.email))
    dueno = consultar("SELECT * FROM duenos WHERE id_dueno = ?", (id_dueno,))[0]
    return jsonify(dueno), 201


@app.get("/v1/duenos")
@requiere_api_key(rol="lectura")
def listar_duenos():
    nombre = request.args.get("nombre", "")
    if nombre:
        duenos = consultar("SELECT * FROM duenos WHERE nombre LIKE ?",
                           (f"%{nombre}%",))
    else:
        duenos = consultar("SELECT * FROM duenos ORDER BY nombre")
    return jsonify(duenos), 200


@app.get("/v1/duenos/<int:id_dueno>")
@requiere_api_key(rol="lectura")
def obtener_dueno(id_dueno):
    duenos = consultar("SELECT * FROM duenos WHERE id_dueno = ?", (id_dueno,))
    if not duenos:
        abort(404)
    return jsonify(duenos[0]), 200


# ============================================================
# Bloques (proxy hacia Agenda)
# ============================================================
@app.get("/v1/bloques")
@requiere_api_key(rol="lectura")
def listar_bloques():
    cacheados = leer_bloques_cacheados()
    if cacheados is not None:
        return jsonify(cacheados), 200

    try:
        bloques = agenda_client.listar_bloques()
    except agenda_client.AgendaTimeoutError:
        abort(504)
    except agenda_client.AgendaNoDisponibleError:
        abort(503)

    guardar_bloques_cacheados(bloques)
    return jsonify(bloques), 200


@app.get("/v1/bloques/<int:id_bloque>")
@requiere_api_key(rol="lectura")
def obtener_bloque(id_bloque):
    """Consulta un veterinario y sus cupos libres en un bloque específico."""
    try:
        bloque = agenda_client.obtener_bloque(id_bloque)
    except agenda_client.AgendaTimeoutError:
        abort(504)
    except agenda_client.AgendaNoDisponibleError:
        abort(503)
    return jsonify(bloque), 200


# ============================================================
# Reservas
# ============================================================
@app.post("/v1/reservas")
@requiere_api_key(rol="escritura")
def crear_reserva():
    datos = cuerpo_json(NuevaReserva)
    clave = request.headers.get(CABECERA_IDEMPOTENCIA)
    body_hash = _hash_cuerpo(datos)

    estado_idemp, reserva_previa = reclamar_clave_idempotencia(clave, body_hash)
    if estado_idemp == "COMPLETADA":
        return jsonify(reserva_previa), 200
    if estado_idemp == "EN_PROCESO":
        return jsonify({
            "error": "PETICION_EN_CURSO",
            "detalle": "Ya hay una petición en curso con la misma Idempotency-Key"
        }), 409
    if estado_idemp == "CUERPO_DISTINTO":
        return jsonify({
            "error": "IDEMPOTENCIA_INVALIDA",
            "detalle": "La Idempotency-Key ya fue utilizada con otros parámetros de reserva"
        }), 422

    try:
        # 1) El dueño tiene que existir en nuestra base.
        if not consultar("SELECT id_dueno FROM duenos WHERE id_dueno = ?",
                         (datos.id_dueno,)):
            liberar_clave_idempotencia(clave)
            abort(404)

        # 2) Pedimos el cupo a Agenda (gRPC).
        try:
            resultado = agenda_client.reservar_cupo(datos.id_bloque)
        except agenda_client.AgendaTimeoutError:
            liberar_clave_idempotencia(clave)
            abort(504)
        except agenda_client.AgendaNoDisponibleError:
            liberar_clave_idempotencia(clave)
            abort(503)
        except (agenda_client.BloqueNoEncontradoError, agenda_client.ReglaNegocioAgendaError):
            liberar_clave_idempotencia(clave)
            raise

        if not resultado["exito"]:
            liberar_clave_idempotencia(clave)
            return jsonify({"error": "SIN_CUPO",
                            "detalle": resultado["mensaje"]}), 409

        # 3) Con el cupo asegurado, guardamos la copia de la cita.
        bloque = resultado["bloque"]
        id_reserva = ejecutar(
            """INSERT INTO reservas
                 (id_dueno, id_bloque, nombre_veterinario, fecha,
                  hora_inicio, mascota_nombre, motivo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datos.id_dueno, datos.id_bloque, bloque["nombre_veterinario"],
             bloque["fecha"], bloque["hora_inicio"], datos.mascota_nombre,
             datos.motivo))
        reserva = consultar("SELECT * FROM reservas WHERE id_reserva = ?",
                            (id_reserva,))[0]

        olvidar_bloques()
        confirmar_reserva_idempotente(clave, body_hash, reserva)
        return jsonify(reserva), 201
    except Exception:
        liberar_clave_idempotencia(clave)
        raise


@app.get("/v1/reservas")
@requiere_api_key(rol="lectura")
def listar_reservas():
    condiciones = []
    params = []
    if request.args.get("id_dueno"):
        condiciones.append("id_dueno = ?")
        params.append(request.args["id_dueno"])
    if request.args.get("estado"):
        condiciones.append("estado = ?")
        params.append(request.args["estado"])

    where = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    reservas = consultar("SELECT * FROM reservas" + where +
                         " ORDER BY creada_en DESC", params)
    return jsonify(reservas), 200


@app.get("/v1/reservas/<int:id_reserva>")
@requiere_api_key(rol="lectura")
def obtener_reserva(id_reserva):
    reservas = consultar("SELECT * FROM reservas WHERE id_reserva = ?",
                         (id_reserva,))
    if not reservas:
        abort(404)
    datos = reservas[0]

    enlaces = {
        "self": f"/v1/reservas/{id_reserva}",
        "dueno": f"/v1/duenos/{datos['id_dueno']}"
    }
    if datos["estado"] != "cancelada":
        enlaces["cancelar"] = {
            "href": f"/v1/reservas/{id_reserva}",
            "metodo": "DELETE"
        }
    datos["_links"] = enlaces

    return jsonify(datos), 200


@app.delete("/v1/reservas/<int:id_reserva>")
@requiere_api_key(rol="escritura")
def cancelar_reserva(id_reserva):
    """Cancela una reserva de forma atómica y libera el cupo en Agenda."""
    reservas = consultar("SELECT * FROM reservas WHERE id_reserva = ?",
                         (id_reserva,))
    if not reservas:
        abort(404)
    reserva = reservas[0]

    # 1) UPDATE condicional atómico: solo un hilo logra pasar de 'activa' a 'cancelada'.
    filas_modificadas = actualizar(
        "UPDATE reservas SET estado = 'cancelada' WHERE id_reserva = ? AND estado = 'activa'",
        (id_reserva,)
    )
    if filas_modificadas == 0:
        return jsonify({"error": "YA_CANCELADA",
                        "detalle": "La reserva ya estaba cancelada"}), 409

    # 2) Solo el hilo que modificó la fila libera el cupo en Agenda.
    # Si Agenda falla, revertimos el estado local a 'activa' para mantener consistencia.
    try:
        agenda_client.liberar_cupo(reserva["id_bloque"])
    except agenda_client.AgendaTimeoutError:
        actualizar("UPDATE reservas SET estado = 'activa' WHERE id_reserva = ?", (id_reserva,))
        abort(504)
    except agenda_client.AgendaNoDisponibleError:
        actualizar("UPDATE reservas SET estado = 'activa' WHERE id_reserva = ?", (id_reserva,))
        abort(503)

    olvidar_bloques()
    return "", 204


# ============================================================
# Healthcheck
# ============================================================
@app.get("/v1/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)