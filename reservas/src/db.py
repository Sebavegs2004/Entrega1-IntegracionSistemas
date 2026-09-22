import sqlite3
import os

DB_PATH = os.environ.get("RESERVAS_DB_PATH", "/data/reservas.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS dueno (
            id        TEXT PRIMARY KEY,
            nombre    TEXT NOT NULL,
            telefono  TEXT NOT NULL,
            email     TEXT
        );

        CREATE TABLE IF NOT EXISTS reserva (
            id                TEXT PRIMARY KEY,
            id_dueno          TEXT NOT NULL REFERENCES dueno(id),
            id_veterinario    TEXT NOT NULL,
            id_bloque         TEXT NOT NULL,
            mascota_nombre    TEXT NOT NULL,
            estado            TEXT NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa','cancelada')),
            idempotency_key   TEXT UNIQUE,
            creado_en         TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
    conn.close()
