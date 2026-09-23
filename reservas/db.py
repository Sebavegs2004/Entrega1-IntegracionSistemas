# ============================================================
# Conexión a MySQL del servicio Reservas.
# Importante: es una base DISTINTA a la de Agenda; este servicio
# nunca toca la base de Agenda (integración solo por gRPC).
# ============================================================
import os

import mysql.connector


def get_conn():
    """Crea y devuelve una conexión a la base de datos de Reservas."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "reservas"),
        password=os.environ.get("DB_PASSWORD", "reservas123"),
        database=os.environ.get("DB_NAME", "reservas_db"),
    )


def get_dict_cursor(conn):
    """Devuelve un cursor que entrega cada fila como diccionario."""
    return conn.cursor(dictionary=True)