# ============================================================
# Conexión a la base de datos del servicio Reservas (SQLite).
# Importante: es una base DISTINTA a la de Agenda; este servicio
# nunca toca la base de Agenda (integración solo por gRPC).
# ============================================================
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/data/reservas.db")
CARPETA_SQL = Path(__file__).resolve().parent / "sql"
RUTA_ESQUEMA = "reservas.sql"


def inicializar():
    """Crea las tablas si no existen, leyendo sql/reservas.sql."""
    conn = _conexion()
    try:
        conn.executescript(_leer_script(RUTA_ESQUEMA))
        conn.commit()
    finally:
        conn.close()


def consultar(sql, params=()):
    """Ejecuta una consulta (SELECT) y devuelve las filas como diccionarios."""
    conn = _conexion()
    try:
        return [dict(f) for f in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def ejecutar(sql, params=()):
    """Ejecuta un INSERT y devuelve el id de la fila insertada (lastrowid)."""
    conn = _conexion()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def actualizar(sql, params=()):
    """Ejecuta un UPDATE o DELETE condicional y devuelve cuántas filas
    cambiaron realmente (rowcount). Clave para evitar condiciones de carrera."""
    conn = _conexion()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _conexion():
    """Crea y devuelve una conexión a la base de datos de Reservas."""
    carpeta = Path(DB_PATH).parent
    carpeta.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _leer_script(nombre):
    """Lee un script .sql de la carpeta sql/ del proyecto."""
    ruta = CARPETA_SQL / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el script {ruta}")
    return ruta.read_text(encoding="utf-8")