# ============================================================
# Conexión a MySQL del servicio Agenda.
# Los datos de conexión llegan por variables de entorno
# (las define docker-compose.yml).
# ============================================================
import os

import mysql.connector


def get_conn():
    """Crea y devuelve una conexión a la base de datos de Agenda."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "agenda"),
        password=os.environ.get("DB_PASSWORD", "agenda123"),
        database=os.environ.get("DB_NAME", "agenda_db"),
    )


def get_dict_cursor(conn):
    """Devuelve un cursor que entrega cada fila como diccionario.
    Ej: {"id_bloque": 3, "cupos_libres": 2} — más cómodo que tuplas.
    """
    return conn.cursor(dictionary=True)