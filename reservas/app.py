# ============================================================
# Servicio Reservas (Flask) — Clínica Veterinaria VidaAnimal
#
#   - Expone la API REST pública bajo /v1 (autenticada con API Key)
#   - Sirve la interfaz web (index.html + Bootstrap 5 + Vanilla JS)
#   - Se integra con Agenda SOLO a través del cliente gRPC
#     (agenda_client.py). Nunca se conecta a la base de Agenda.
#
# La base de datos propia es un archivo SQLite (ver db.py).
# ============================================================
import json
import os
from functools import wraps
from pathlib import Path

import redis
import yaml
from flask import Flask, abort, jsonify, render_template, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

import agenda_client   # nuestro cliente gRPC hacia Agenda
from db import consultar, ejecutar, inicializar

app = Flask(__name__)

# Configuración (las variables de entorno las define docker-compose.yml).
API_KEY = os.environ.get("API_KEY", "clave-secreta-vet-2026")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis_cache")

# Redis es otro servicio de la red de Docker (nombre en docker-compose.yml).
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=6379,
    db=0,
    decode_responses=True
)

# ============================================================
# Constantes de configuración
# ============================================================
# El contrato OpenAPI viaja dentro de la imagen: el Dockerfile hace
# "COPY contracts/ contracts/", así que queda en /app/contracts.
# Swagger UI lo lee desde ahí, no hay ninguna copia ni ruta aparte.
RUTA_CONTRATO = Path(app.root_path) / "contracts" / "openapi.yaml"

# Cabecera que permite NO crear dos veces la misma reserva.
CABECERA_IDEMPOTENCIA = "Idempotency-Key"

# Redis: clave de la caché de bloques, segundos que se guarda y
# segundos que se recuerda la respuesta de una reserva idempotente.
CLAVE_BLOQUES = "cache:bloques"
TTL_BLOQUES = 60          # 1 minuto
TTL_IDEMPOTENCIA = 86400  # 24 horas


# ============================================================
# Autenticación con API Key (header X-API-Key)
# Es el mecanismo más simple de explicar y cumple el requisito:
# cada petición debe llevar la clave en el header, y un decorador
# la valida antes de ejecutar la ruta. Es como una "contraseña"
# global para consumir la API.
# ============================================================
def requiere_api_key(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        clave = request.headers.get("X-API-Key")
        if not clave:
            return jsonify({"error": "NO_AUTORIZADO",
                            "detalle": "Falta el header X-API-Key"}), 401
        if clave != API_KEY:
            return jsonify({"error": "NO_AUTORIZADO",
                            "detalle": "API Key inválida"}), 401
        return f(*args, **kwargs)
    return envoltura


# ============================================================
# Validación de la entrada
# Los modelos de Pydantic dicen qué campos espera cada cuerpo. Si algo
# no cumple, se lanza DatosInvalidos y el manejador de más abajo
# responde 400, así que las rutas NO repiten validaciones a mano.
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
    email: str | None = None


class NuevaReserva(BaseModel):
    """Cuerpo de POST /v1/reservas."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    id_dueno: int = Field(ge=1)
    id_bloque: int = Field(ge=1)
    mascota_nombre: str = Field(min_length=1)
    motivo: str | None = None


def cuerpo_json(modelo):
    """Devuelve el cuerpo de la petición ya validado con el modelo dado.

    get_json() va SIN silent=True a propósito: si el cuerpo no llega
    como JSON, Flask lanza el error 415 y lo atiende el manejador de
    más abajo. Si llega, Pydantic se encarga del resto.
    """
    datos = request.get_json()
    if not isinstance(datos, dict):
        raise DatosInvalidos("El cuerpo JSON debe ser un objeto")
    try:
        return modelo.model_validate(datos)
    except ValidationError as e:
        campos = [n for n, f in modelo.model_fields.items() if f.is_required()]
        raise DatosInvalidos(
            f"Revisa los campos obligatorios: {', '.join(campos)}") from e


# ============================================================
# Manejadores globales de errores HTTP
# Todas las respuestas de error usan el mismo formato del contrato
# REST: {"error": "<CODIGO>", "detalle": "<texto>"}.
#
# Cada código HTTP se escribe UNA sola vez, aquí en su manejador.
# Las rutas no construyen el JSON: solo llaman a abort(codigo), que
# lanza el error y Flask encamina la respuesta por el manejador.
# Gracias a eso, un 404 dice lo mismo en todos los casos posibles
# (un dueño que no existe, una reserva que no existe, una URL mal
# escrita) y el consumidor nunca recibe HTML por error.
# ============================================================
@app.errorhandler(DatosInvalidos)
def datos_invalidos(e):
    return jsonify({"error": "DATOS_INVALIDOS",
                    "detalle": e.detalle}), 400


@app.errorhandler(400)
def peticion_malformada(e):
    # El cuerpo dice que es JSON pero está roto: no se pudo interpretar.
    return jsonify({"error": "DATOS_INVALIDOS",
                    "detalle": "La petición no es válida. "
                               "Revisa los datos enviados."}), 400


@app.errorhandler(404)
def no_encontrado(e):
    # Lo lanzan las rutas con abort(404) cuando el recurso no está en
    # la base, y Flask cuando la URL no coincide con ninguna ruta.
    return jsonify({"error": "NO_ENCONTRADO",
                    "detalle": "Recurso no encontrado"}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"error": "METODO_NO_PERMITIDO",
                    "detalle": "El método HTTP no está permitido "
                               "para esta ruta."}), 405


@app.errorhandler(415)
def contenido_no_soportado(e):
    # Flask lanza este error cuando request.get_json() recibe un cuerpo
    # que no viene como application/json.
    return jsonify({"error": "CONTENIDO_NO_SOPORTADO",
                    "detalle": "El cuerpo de la petición debe ser JSON "
                               "(Content-Type: application/json)."}), 415


@app.errorhandler(500)
def error_interno(e):
    # No se devuelve la excepción real al cliente: solo un mensaje
    # general. El detalle queda en el log del servidor.
    return jsonify({"error": "ERROR_INTERNO",
                    "detalle": "Ocurrió un error inesperado "
                               "en el servidor."}), 500


@app.errorhandler(503)
def agenda_no_disponible(e):
    # Lo lanzan las rutas con abort(503) cuando el cliente gRPC no logra
    # hablar con Agenda en el plazo de espera.
    return jsonify({"error": "AGENDA_NO_DISPONIBLE",
                    "detalle": "El servicio de Agenda no está disponible. "
                               "Intenta de nuevo en un momento."}), 503


# ============================================================
# Redis (caché de bloques e idempotencia)
# Redis es una ayuda, nunca una obligación: si está caído, la API sigue
# funcionando y solo pierde la caché.
# ============================================================
def leer_bloques_cacheados():
    """Bloques guardados en Redis, o None si no hay caché o Redis falla."""
    try:
        guardado = redis_client.get(CLAVE_BLOQUES)
        return json.loads(guardado) if guardado else None
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al leer la caché: %s", e)
        return None


def guardar_bloques_cacheados(bloques):
    """Guarda la lista de bloques recién consultada a Agenda."""
    try:
        redis_client.setex(CLAVE_BLOQUES, TTL_BLOQUES, json.dumps(bloques))
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al guardar la caché: %s", e)


def olvidar_bloques():
    """Borra la caché de bloques: un cupo se acaba de ocupar o liberar."""
    try:
        redis_client.delete(CLAVE_BLOQUES)
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al borrar la caché: %s", e)


def leer_reserva_idempotente(clave):
    """Reserva ya creada para esa clave de idempotencia, o None."""
    if not clave:
        return None
    try:
        guardado = redis_client.get(f"idemp:reserva:{clave}")
        return json.loads(guardado) if guardado else None
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al leer la idempotencia: %s", e)
        return None


def guardar_reserva_idempotente(clave, reserva):
    """Recuerda la respuesta exitosa para no repetirla en otra petición."""
    if not clave:
        return
    try:
        redis_client.setex(f"idemp:reserva:{clave}", TTL_IDEMPOTENCIA,
                           json.dumps(reserva))
    except redis.RedisError as e:
        app.logger.warning("Redis no respondió al guardar la idempotencia: %s", e)


# ============================================================
# Interfaz web
# ============================================================
@app.get("/")
def index():
    """Sirve la página principal (Bootstrap 5 + Vanilla JS)."""
    return render_template("index.html")


@app.get("/v1/docs")
def docs():
    """Swagger UI. La especificación se lee del contrato y se le pasa a
    la plantilla, así contracts/openapi.yaml es la única copia."""
    with open(RUTA_CONTRATO, encoding="utf-8") as archivo:
        contrato = yaml.safe_load(archivo)
    return render_template("swagger.html", contrato=contrato)


# ============================================================
# Dueños
# ============================================================
@app.post("/v1/duenos")
@requiere_api_key
def crear_dueno():
    """Registra un dueño de mascota."""
    datos = cuerpo_json(NuevoDueno)
    id_dueno = ejecutar(
        "INSERT INTO duenos (nombre, telefono, email) VALUES (?, ?, ?)",
        (datos.nombre, datos.telefono, datos.email))
    dueno = consultar("SELECT * FROM duenos WHERE id_dueno = ?", (id_dueno,))[0]
    return jsonify(dueno), 201


@app.get("/v1/duenos")
@requiere_api_key
def listar_duenos():
    """Lista los dueños, opcionalmente filtrando por nombre."""
    nombre = request.args.get("nombre", "")
    if nombre:
        duenos = consultar("SELECT * FROM duenos WHERE nombre LIKE ?",
                           (f"%{nombre}%",))
    else:
        duenos = consultar("SELECT * FROM duenos ORDER BY nombre")
    return jsonify(duenos), 200


@app.get("/v1/duenos/<int:id_dueno>")
@requiere_api_key
def obtener_dueno(id_dueno):
    """Devuelve un dueño por su id."""
    duenos = consultar("SELECT * FROM duenos WHERE id_dueno = ?", (id_dueno,))
    if not duenos:
        abort(404)
    return jsonify(duenos[0]), 200


# ============================================================
# Bloques (proxy hacia Agenda) — lo usa la interfaz web
# ============================================================
@app.get("/v1/bloques")
@requiere_api_key
def listar_bloques():
    """Pide la lista de bloques a Agenda vía gRPC y la devuelve como JSON.

    La respuesta se guarda en Redis, así que los cupos pueden demorar
    un poco en reflejarse después de reservar o cancelar.
    """
    cacheados = leer_bloques_cacheados()
    if cacheados is not None:
        return jsonify(cacheados), 200

    try:
        bloques = agenda_client.listar_bloques()
    except agenda_client.AgendaNoDisponibleError:
        abort(503)

    guardar_bloques_cacheados(bloques)
    return jsonify(bloques), 200


# ============================================================
# Reservas
# ============================================================
@app.post("/v1/reservas")
@requiere_api_key
def crear_reserva():
    """Crea una reserva: primero asegura el cupo en Agenda (gRPC)
    y después guarda la copia de la cita en nuestra base."""
    clave = request.headers.get(CABECERA_IDEMPOTENCIA)
    repetida = leer_reserva_idempotente(clave)
    if repetida:
        return jsonify(repetida), 200

    datos = cuerpo_json(NuevaReserva)

    # 1) El dueño tiene que existir en NUESTRA base.
    if not consultar("SELECT id_dueno FROM duenos WHERE id_dueno = ?",
                     (datos.id_dueno,)):
        abort(404)

    # 2) Pedimos el cupo a Agenda (gRPC).
    try:
        resultado = agenda_client.reservar_cupo(datos.id_bloque)
    except agenda_client.AgendaNoDisponibleError:
        abort(503)

    if not resultado["exito"]:
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

    olvidar_bloques()          # quedó un cupo menos disponible
    guardar_reserva_idempotente(clave, reserva)

    return jsonify(reserva), 201


@app.get("/v1/reservas")
@requiere_api_key
def listar_reservas():
    """Lista las reservas, opcionalmente filtrando por dueño y estado."""
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
@requiere_api_key
def obtener_reserva(id_reserva):
    """Devuelve una reserva por su id, con enlaces HATEOAS."""
    reservas = consultar("SELECT * FROM reservas WHERE id_reserva = ?",
                         (id_reserva,))
    if not reservas:
        abort(404)
    datos = reservas[0]

    # Enlaces HATEOAS: la respuesta publica las acciones disponibles
    # en lugar de dejar que el cliente adivine las URLs.
    enlaces = {
        "self": f"/v1/reservas/{id_reserva}",
        "dueno": f"/v1/duenos/{datos['id_dueno']}"
    }
    # Si la reserva sigue activa, le sugerimos al cliente que puede cancelarla
    if datos["estado"] != "cancelada":
        enlaces["cancelar"] = {
            "href": f"/v1/reservas/{id_reserva}",
            "metodo": "DELETE"
        }
    datos["_links"] = enlaces

    return jsonify(datos), 200


@app.delete("/v1/reservas/<int:id_reserva>")
@requiere_api_key
def cancelar_reserva(id_reserva):
    """Cancela una reserva y libera el cupo en Agenda."""
    reservas = consultar("SELECT * FROM reservas WHERE id_reserva = ?",
                         (id_reserva,))
    if not reservas:
        abort(404)
    reserva = reservas[0]
    if reserva["estado"] == "cancelada":
        return jsonify({"error": "YA_CANCELADA",
                        "detalle": "La reserva ya estaba cancelada"}), 409

    # Liberamos el cupo en Agenda (gRPC). Si discutible soltar el
    # cupo primero o marcar después; en este MVP basta con esto.
    try:
        agenda_client.liberar_cupo(reserva["id_bloque"])
    except agenda_client.AgendaNoDisponibleError:
        abort(503)

    ejecutar("UPDATE reservas SET estado = 'cancelada' WHERE id_reserva = ?",
             (id_reserva,))
    olvidar_bloques()          # volvió a quedar un cupo libre

    return "", 204


# ============================================================
# Healthcheck (lo usa docker-compose para saber si está arriba)
# ============================================================
@app.get("/v1/health")
def health():
    """Indica que el servicio está arriba (no pide API Key)."""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # Crea el archivo SQLite y sus tablas (solo si no existen).
    # Los datos se guardan en el volumen de Docker (/data), así que
    # siguen ahí aunque se reconstruya el contenedor.
    inicializar()
    app.run(host="0.0.0.0", port=5000)
