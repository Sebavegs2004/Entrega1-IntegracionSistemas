# ============================================================
# Conexión a la base de datos del servicio Agenda (SQLite).
#
# SQLite es una base en un archivo: no hay servidor, ni usuario,
# ni contraseña, solo la ruta del archivo (DB_PATH), que le llega
# por variable de entorno desde docker-compose.yml y apunta al
# volumen del contenedor. El módulo sqlite3 viene con Python, no
# hay que instalar nada.
# ============================================================
import os
import sqlite3
from pathlib import Path

# Ruta del archivo SQLite.
DB_PATH = os.environ.get("DB_PATH", "/data/agenda.db")

# Los scripts .sql se leen de la carpeta sql/ del proyecto, que el
# Dockerfile copia en /app/sql.
CARPETA_SQL = Path(__file__).resolve().parent / "sql"

# Scripts .sql del proyecto: el primero crea las tablas y el
# segundo trae los datos de ejemplo.
RUTA_ESQUEMA = "agenda.sql"
RUTA_SEED = "agenda_seed.sql"


def get_conn():
    """Crea y devuelve una conexión a la base de datos de Agenda."""
    carpeta = Path(DB_PATH).parent
    carpeta.mkdir(parents=True, exist_ok=True)   # por si la carpeta no existe
    conn = sqlite3.connect(DB_PATH, timeout=10)
    # row_factory hace que cada fila se pueda leer como un
    # diccionario: fila["cupos_libres"] (en vez de fila[5]).
    conn.row_factory = sqlite3.Row
    # SQLite no aplica las claves foráneas por defecto.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def inicializar():
    """Crea las tablas si no existen y carga los datos de ejemplo
    SOLO si la base está vacía.

    Así los datos de ejemplo se cargan una vez y no se repiten en
    cada arranque del contenedor.
    """
    conn = get_conn()
    try:
        conn.executescript(_leer_script(RUTA_ESQUEMA))
        # Si ya hay veterinarios guardados, la base ya tiene datos:
        # no cargamos el seed para no duplicarlos.
        total = conn.execute("SELECT COUNT(*) FROM veterinarios").fetchone()[0]
        if total == 0:
            conn.executescript(_leer_script(RUTA_SEED))
        conn.commit()
    finally:
        conn.close()


def _leer_script(nombre):
    """Lee un script .sql de la carpeta sql/ del proyecto.

    El Dockerfile los copia a /app/sql, así que la ruta siempre
    es la misma.
    """
    ruta = CARPETA_SQL / nombre
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró el script {ruta}")
    return ruta.read_text(encoding="utf-8")
