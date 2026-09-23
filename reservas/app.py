# ============================================================
# Servicio Reservas (Flask) — Clínica Veterinaria VidaAnimal
#
#   - Expone la API REST pública bajo /v1 (autenticada con API Key)
#   - Sirve la interfaz web (index.html + Bootstrap 5 + Vanilla JS)
#   - Se integra con Agenda SOLO a través del cliente gRPC
#     (agenda_client.py). Nunca se conecta a la base de Agenda.
# ============================================================
import os
from datetime import date, datetime
from functools import wraps

from flask import Flask, jsonify, render_template, request, send_file

import agenda_client   # nuestro cliente gRPC hacia Agenda
from db import get_conn, get_dict_cursor

app = Flask(__name__)

# ============================================================
# Autenticación con API Key (header X-API-Key)
# Es el mecanismo más simple de explicar y cumple el requisito:
# cada petición debe llevar la clave en el header, y un decorador
# la valida antes de ejecutar la ruta. Es como una "contraseña"
# global para consumir la API.
# ============================================================
API_KEY = os.environ.get("API_KEY", "clave-secreta-vet-2026")


def requiere_api_key(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        clave = request.headers.get("X-API-Key")
        if not clave:
            return jsonify({"error": "NO_AUTORIZADO",
                            "mensaje": "Falta el header X-API-Key"}), 401
        if clave != API_KEY:
            return jsonify({"error": "NO_AUTORIZADO",
                            "mensaje": "API Key inválida"}), 401
        return f(*args, **kwargs)
    return envoltura


def serializar(filas):
    """Convierte fechas y horas a texto para poder enviarlas como JSON."""
    resultado = []
    for f in filas:
        f = dict(f)
        if isinstance(f.get("fecha"), (date, datetime)):
            f["fecha"] = str(f["fecha"])
        if isinstance(f.get("creada_en"), datetime):
            f["creada_en"] = str(f["creada_en"])
        resultado.append(f)
    return resultado


# ============================================================
# Interfaz web
# ============================================================
@app.get("/")
def index():
    """Sirve la página principal (Bootstrap 5 + Vanilla JS)."""
    return render_template("index.html")


# ============================================================
# Documentación de la API (Swagger UI + spec OpenAPI)
# ============================================================
@app.get("/openapi.yaml")
def openapi():
    """Sirve la especificación OpenAPI del contrato REST.
    Se busca primero la ubicación dentro del contenedor y luego la local."""
    rutas = [
        os.path.join(app.root_path, "contracts", "openapi.yaml"),          # en Docker (/app/contracts)
        os.path.join(os.path.dirname(__file__), "..", "contracts",         # en local (./contracts)
                     "openapi.yaml"),
    ]
    for r in rutas:
        if os.path.exists(r):
            return send_file(r, mimetype="text/yaml")
    return jsonify({"error": "NO_ENCONTRADO",
                    "mensaje": "No se encontró el archivo openapi.yaml"}), 404


@app.get("/swagger")
def swagger():
    """Interfaz gráfica de Swagger UI (carga desde el CDN, sin dependencias)."""
    return render_template("swagger.html")


# ============================================================
# Dueños
# ============================================================
@app.post("/v1/duenos")
@requiere_api_key
def crear_dueno():
    datos = request.get_json(silent=True) or {}
    nombre = (datos.get("nombre") or "").strip()
    telefono = (datos.get("telefono") or "").strip()
    email = (datos.get("email") or "").strip() or None

    if not nombre or not telefono:
        return jsonify({"error": "DATOS_INVALIDOS",
                        "mensaje": "'nombre' y 'telefono' son obligatorios"}), 400

    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        cur.execute(
            "INSERT INTO duenos (nombre, telefono, email) VALUES (%s, %s, %s)",
            (nombre, telefono, email))
        conn.commit()
        # LAST_INSERT_ID() devuelve el id recién generado
        cur.execute("SELECT * FROM duenos WHERE id_dueno = LAST_INSERT_ID()")
        dueno = cur.fetchone()
    finally:
        conn.close()
    return jsonify(serializar([dueno])[0]), 201


@app.get("/v1/duenos")
@requiere_api_key
def listar_duenos():
    nombre = request.args.get("nombre")
    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        if nombre:
            cur.execute("SELECT * FROM duenos WHERE nombre LIKE %s",
                        (f"%{nombre}%",))
        else:
            cur.execute("SELECT * FROM duenos ORDER BY nombre")
        filas = cur.fetchall()
    finally:
        conn.close()
    return jsonify(serializar(filas)), 200


@app.get("/v1/duenos/<int:id_dueno>")
@requiere_api_key
def obtener_dueno(id_dueno):
    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        cur.execute("SELECT * FROM duenos WHERE id_dueno = %s", (id_dueno,))
        dueno = cur.fetchone()
    finally:
        conn.close()
    if dueno is None:
        return jsonify({"error": "NO_ENCONTRADO",
                        "mensaje": "El dueño no existe"}), 404
    return jsonify(serializar([dueno])[0]), 200


# ============================================================
# Bloques (proxy hacia Agenda) — lo usa la interfaz web
# ============================================================
@app.get("/v1/bloques")
@requiere_api_key
def listar_bloques():
    """Pide la lista de bloques a Agenda vía gRPC y la devuelve como JSON.
    Si Agenda está caída respondemos 503 (Servicio no disponible)."""
    try:
        bloques = agenda_client.listar_bloques()
    except agenda_client.AgendaNoDisponibleError:
        return jsonify({"error": "AGENDA_NO_DISPONIBLE",
                        "mensaje": "El servicio de Agenda no está disponible. "
                                   "Intenta de nuevo en un momento."}), 503
    return jsonify(bloques), 200


# ============================================================
# Reservas
# ============================================================
@app.post("/v1/reservas")
@requiere_api_key
def crear_reserva():
    datos = request.get_json(silent=True) or {}
    id_dueno = datos.get("id_dueno")
    id_bloque = datos.get("id_bloque")
    mascota = (datos.get("mascota_nombre") or "").strip()
    motivo = (datos.get("motivo") or "").strip() or None

    if not id_dueno or not id_bloque or not mascota:
        return jsonify({"error": "DATOS_INVALIDOS",
                        "mensaje": "'id_dueno', 'id_bloque' y 'mascota_nombre' "
                                   "son obligatorios"}), 400

    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)

        # 1) Verificamos que el dueño exista en NUESTRA base.
        cur.execute("SELECT id_dueno FROM duenos WHERE id_dueno = %s",
                    (id_dueno,))
        if cur.fetchone() is None:
            return jsonify({"error": "DUENO_NO_EXISTE",
                            "mensaje": "El dueño indicado no existe"}), 404

        # 2) Pedimos el cupo a Agenda (gRPC). Este es el punto de
        #    integración: si Agenda está caída -> 503 y NO insertamos nada.
        try:
            resultado = agenda_client.reservar_cupo(id_bloque)
        except agenda_client.AgendaNoDisponibleError:
            return jsonify({"error": "AGENDA_NO_DISPONIBLE",
                            "mensaje": "El servicio de Agenda no respondió. "
                                       "Intenta de nuevo en un momento."}), 503

        if not resultado["exito"]:
            return jsonify({"error": "SIN_CUPO",
                            "mensaje": resultado["mensaje"]}), 409

        # 3) Si todo bien, guardamos la reserva. Guardamos también una
        #    COPIA de los datos de la cita (vienen en la respuesta de
        #    Agenda) para mostrarla en la UI sin depender de Agenda.
        bloque = resultado["bloque"]
        cur.execute(
            """INSERT INTO reservas
                 (id_dueno, id_bloque, nombre_veterinario, fecha,
                  hora_inicio, mascota_nombre, motivo)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (id_dueno, id_bloque, bloque["nombre_veterinario"],
             bloque["fecha"], bloque["hora_inicio"], mascota, motivo))
        conn.commit()

        cur.execute("SELECT * FROM reservas WHERE id_reserva = LAST_INSERT_ID()")
        reserva = cur.fetchone()
    finally:
        conn.close()
    return jsonify(serializar([reserva])[0]), 201


@app.get("/v1/reservas")
@requiere_api_key
def listar_reservas():
    id_dueno = request.args.get("id_dueno")
    estado = request.args.get("estado")

    sql = "SELECT * FROM reservas WHERE 1 = 1"
    params = []
    if id_dueno:
        sql += " AND id_dueno = %s"
        params.append(id_dueno)
    if estado:
        sql += " AND estado = %s"
        params.append(estado)
    sql += " ORDER BY creada_en DESC"

    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        cur.execute(sql, params)
        filas = cur.fetchall()
    finally:
        conn.close()
    return jsonify(serializar(filas)), 200


@app.get("/v1/reservas/<int:id_reserva>")
@requiere_api_key
def obtener_reserva(id_reserva):
    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        cur.execute("SELECT * FROM reservas WHERE id_reserva = %s",
                    (id_reserva,))
        reserva = cur.fetchone()
    finally:
        conn.close()
    if reserva is None:
        return jsonify({"error": "NO_ENCONTRADA",
                        "mensaje": "La reserva no existe"}), 404
    return jsonify(serializar([reserva])[0]), 200


@app.delete("/v1/reservas/<int:id_reserva>")
@requiere_api_key
def cancelar_reserva(id_reserva):
    conn = get_conn()
    try:
        cur = get_dict_cursor(conn)
        cur.execute("SELECT * FROM reservas WHERE id_reserva = %s",
                    (id_reserva,))
        reserva = cur.fetchone()
        if reserva is None:
            return jsonify({"error": "NO_ENCONTRADA",
                            "mensaje": "La reserva no existe"}), 404
        if reserva["estado"] == "cancelada":
            return jsonify({"error": "YA_CANCELADA",
                            "mensaje": "La reserva ya estaba cancelada"}), 409

        # Liberamos el cupo en Agenda (gRPC). Si discutible soltar el
        # cupo primero o marcar después; en este MVP basta con esto.
        try:
            agenda_client.liberar_cupo(reserva["id_bloque"])
        except agenda_client.AgendaNoDisponibleError:
            return jsonify({"error": "AGENDA_NO_DISPONIBLE",
                            "mensaje": "No se pudo liberar el cupo en Agenda. "
                                       "Intenta de nuevo."}), 503

        cur.execute("UPDATE reservas SET estado = 'cancelada' "
                    "WHERE id_reserva = %s", (id_reserva,))
        conn.commit()
    finally:
        conn.close()
    return "", 204


# ============================================================
# Healthcheck (lo usa docker-compose para saber si está arriba)
# ============================================================
@app.get("/v1/health")
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # El esquema de la base ya existe gracias a sql/reservas.sql
    # (se carga al iniciar el contenedor de MySQL), por eso aquí solo
    # arrancamos la aplicación.
    app.run(host="0.0.0.0", port=5000)