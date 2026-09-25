# ============================================================
# Conexión a la base de datos del servicio Reservas (SQLite).
# Importante: es una base DISTINTA a la de Agenda; este servicio
# nunca toca la base de Agenda (integración solo por gRPC).
#
# SQLite es una base en un archivo, así que no hay servidor, ni
# usuario, ni contraseña: basta con la ruta del archivo, que
# llega por la variable de entorno DB_PATH (la define
# docker-compose.yml y apunta al volumen del contenedor).
# El módulo sqlite3 viene con Python, no hay que instalar nada.
# ============================================================
import os
import sqlite3
from pathlib import Path

# Ruta del archivo SQLite.
DB_PATH = os.environ.get("DB_PATH", "/data/reservas.db")

# Los scripts .sql se leen de la carpeta sql/ del proyecto, que el
# Dockerfile copia en /app/sql.
CARPETA_SQL = Path(__file__).resolve().parent / "sql"

# Nombre del script .sql que crea las tablas.
RUTA_ESQUEMA = "reservas.sql"


def inicializar():
    """Crea las tablas si no existen, leyendo sql/reservas.sql.

    Se ejecuta al arrancar el servicio. Como el script usa
    CREATE TABLE IF NOT EXISTS, los datos que ya están guardados
    no se tocan: solo se agrega lo que falta.
    """
    conn = _conexion()
    try:
        conn.executescript(_leer_script(RUTA_ESQUEMA))
        conn.commit()
    finally:
        conn.close()


def consultar(sql, params=()):
    """Ejecuta una consulta (SELECT) y devuelve las filas.

    Cada fila viene como diccionario, así que en las rutas se usa
    fila["nombre"] en vez de fila[0]. La conexión se abre y se cierra
    sola en cada llamada.
    """
    conn = _conexion()
    try:
        return [dict(f) for f in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def ejecutar(sql, params=()):
    """Ejecuta una escritura (INSERT o UPDATE) y confirma el cambio.

    Devuelve el id de la fila insertada (lastrowid), que sirve para
    leer de vuelta lo recien guardado y responderlo en el JSON.
    """
    conn = _conexion()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _conexion():
    """Crea y devuelve una conexión a la base de datos de Reservas."""
    carpeta = Path(DB_PATH).parent
    carpeta.mkdir(parents=True, exist_ok=True)   # por si la carpeta no existe
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # row_factory hace que cada fila se pueda leer como un
    # diccionario: fila["nombre"] (en vez de fila[0]).
    conn.row_factory = sqlite3.Row
    # SQLite no aplica las claves foráneas por defecto.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _leer_script(nombre):
    """Lee un script .sql de la carpeta sql/ del proyecto.

    El Dockerfile los copia a /app/sql, así que la ruta es siempre
    la misma.
    """
    ruta = CARPETA_SQL / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el script {ruta}")
    return ruta.read_text(encoding="utf-8")

