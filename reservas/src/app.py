import os
import uuid
from functools import wraps

from flask import Flask, request, jsonify

import agenda_client
from db import get_conn, init_db

app = Flask(__name__)

API_KEY = os.environ.get("API_KEY", "clave-secreta-vet-2026")

SERVICIO = "reservas"


# ---------- Auth (T6) ----------
def requiere_api_key(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        clave = request.headers.get("X-API-Key")
        if not clave:
            return jsonify({"error": "NO_AUTORIZADO", "mensaje": "Falta header X-API-Key"}), 401
        if clave != API_KEY:
            return jsonify({"error": "NO_AUTORIZADO", "mensaje": "API Key inválida"}), 401
        return f(*args, **kwargs)
    return wrapper


# ---------- Duenos ----------
@app.post("/v1/duenos")
@requiere_api_key
def crear_dueno():
    data = request.get_json(silent=True) or {}
    nombre = data.get("nombre")
    telefono = data.get("telefono")
    email = data.get("email")

    if not nombre or not telefono:
        return jsonify({"error": "DATOS_INVALIDOS", "mensaje": "nombre y telefono son obligatorios"}), 400

    dueno_id = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO dueno (id, nombre, telefono, email) VALUES (?, ?, ?, ?)",
        (dueno_id, nombre, telefono, email),
    )
    conn.commit()
    conn.close()

    return jsonify({"id": dueno_id, "nombre": nombre, "telefono": telefono, "email": email}), 201


@app.get("/v1/duenos/<id_dueno>")
@requiere_api_key
def obtener_dueno(id_dueno):
    conn = get_conn()
    row = conn.execute("SELECT * FROM dueno WHERE id = ?", (id_dueno,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "NO_ENCONTRADO", "mensaje": "Dueño no existe"}), 404
    return jsonify(dict(row)), 200


@app.get("/v1/duenos")
@requiere_api_key
def listar_duenos():
    nombre = request.args.get("nombre")
    conn = get_conn()
    if nombre:
        rows = conn.execute("SELECT * FROM dueno WHERE nombre LIKE ?", (f"%{nombre}%",)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM dueno").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


# ---------- Reservas ----------
@app.post("/v1/reservas")
@requiere_api_key
def crear_reserva():
    data = request.get_json(silent=True) or {}
    id_dueno = data.get("id_dueno")
    id_veterinario = data.get("id_veterinario")
    id_bloque = data.get("id_bloque")
    mascota_nombre = data.get("mascota_nombre")

    if not all([id_dueno, id_veterinario, id_bloque, mascota_nombre]):
        return jsonify({
            "error": "DATOS_INVALIDOS",
            "mensaje": "id_dueno, id_veterinario, id_bloque y mascota_nombre son obligatorios",
        }), 400

    conn = get_conn()
    dueno = conn.execute("SELECT id FROM dueno WHERE id = ?", (id_dueno,)).fetchone()
    if not dueno:
        conn.close()
        return jsonify({"error": "DUENO_NO_EXISTE", "mensaje": "El dueño no existe"}), 404

    # T7: si Agenda no responde a tiempo, devolvemos 503 y no insertamos nada
    try:
        resultado = agenda_client.reservar_cupo(id_bloque)
    except agenda_client.AgendaNoDisponibleError:
        conn.close()
        return jsonify({
            "error": "AGENDA_NO_DISPONIBLE",
            "mensaje": "El servicio de Agenda no respondió a tiempo, intente nuevamente",
        }), 503

    if not resultado["exito"]:
        conn.close()
        return jsonify({"error": "SIN_CUPO", "mensaje": resultado["mensaje"]}), 409

    reserva_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO reserva (id, id_dueno, id_veterinario, id_bloque, mascota_nombre, estado)
           VALUES (?, ?, ?, ?, ?, 'activa')""",
        (reserva_id, id_dueno, id_veterinario, id_bloque, mascota_nombre),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM reserva WHERE id = ?", (reserva_id,)).fetchone()
    conn.close()

    return jsonify(dict(row)), 201


@app.get("/v1/reservas/<id_reserva>")
@requiere_api_key
def obtener_reserva(id_reserva):
    conn = get_conn()
    row = conn.execute("SELECT * FROM reserva WHERE id = ?", (id_reserva,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "NO_ENCONTRADO", "mensaje": "Reserva no existe"}), 404
    return jsonify(dict(row)), 200


@app.get("/v1/reservas")
@requiere_api_key
def listar_reservas():
    id_dueno = request.args.get("id_dueno")
    estado = request.args.get("estado")

    query = "SELECT * FROM reserva WHERE 1=1"
    params = []
    if id_dueno:
        query += " AND id_dueno = ?"
        params.append(id_dueno)
    if estado:
        query += " AND estado = ?"
        params.append(estado)

    conn = get_conn()
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200


@app.delete("/v1/reservas/<id_reserva>")
@requiere_api_key
def cancelar_reserva(id_reserva):
    conn = get_conn()
    row = conn.execute("SELECT * FROM reserva WHERE id = ?", (id_reserva,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "NO_ENCONTRADO", "mensaje": "Reserva no existe"}), 404
    if row["estado"] == "cancelada":
        conn.close()
        return jsonify({"error": "YA_CANCELADA", "mensaje": "La reserva ya estaba cancelada"}), 409

    try:
        agenda_client.liberar_cupo(row["id_bloque"])
    except agenda_client.AgendaNoDisponibleError:
        conn.close()
        return jsonify({
            "error": "AGENDA_NO_DISPONIBLE",
            "mensaje": "No se pudo liberar el cupo, intente nuevamente",
        }), 503

    conn.execute("UPDATE reserva SET estado = 'cancelada' WHERE id = ?", (id_reserva,))
    conn.commit()
    conn.close()
    return "", 204


@app.get("/v1/health")
def health():
    return jsonify({"status": "ok"}), 200


# ---------- Error handlers ----------
@app.errorhandler(400)
def peticion_invalida(e):
    return jsonify({"error": "peticion_invalida", "detalle": str(e.description),
                    "servicio": SERVICIO}), 400


@app.errorhandler(401)
def no_autorizado(e):
    return jsonify({"error": "no_autorizado", "detalle": str(e.description),
                    "servicio": SERVICIO}), 401


@app.errorhandler(404)
def no_encontrado(e):
    return jsonify({"error": "no_encontrado", "detalle": str(e.description),
                    "servicio": SERVICIO}), 404


@app.errorhandler(405)
def metodo_no_permitido(e):
    return jsonify({"error": "metodo_no_permitido", "detalle": str(e.description),
                    "servicio": SERVICIO}), 405


@app.errorhandler(409)
def conflicto(e):
    return jsonify({"error": "conflicto", "detalle": str(e.description),
                    "servicio": SERVICIO}), 409


@app.errorhandler(422)
def entidad_no_procesable(e):
    return jsonify({"error": "entidad_no_procesable", "detalle": str(e.description),
                    "servicio": SERVICIO}), 422


@app.errorhandler(503)
def servicio_no_disponible(e):
    return jsonify({"error": "servicio_no_disponible", "detalle": str(e.description),
                    "servicio": SERVICIO}), 503


@app.errorhandler(500)
def error_interno(e):
    detalle = str(e.description) if hasattr(e, "description") else str(e)
    return jsonify({"error": "error_interno", "detalle": detalle,
                    "servicio": SERVICIO}), 500


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)
