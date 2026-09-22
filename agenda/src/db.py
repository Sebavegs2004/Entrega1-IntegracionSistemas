import sqlite3
import uuid
import os

DB_PATH = os.environ.get("AGENDA_DB_PATH", "/data/agenda.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS veterinario (
            id           TEXT PRIMARY KEY,
            nombre       TEXT NOT NULL,
            especialidad TEXT
        );

        CREATE TABLE IF NOT EXISTS bloque_horario (
            id                 TEXT PRIMARY KEY,
            id_veterinario     TEXT NOT NULL REFERENCES veterinario(id),
            fecha              TEXT NOT NULL,
            hora_inicio        TEXT NOT NULL,
            hora_fin           TEXT NOT NULL,
            cupos_totales      INTEGER NOT NULL CHECK (cupos_totales >= 0),
            cupos_disponibles  INTEGER NOT NULL CHECK (cupos_disponibles >= 0),
            UNIQUE (id_veterinario, fecha, hora_inicio)
        );
        """
    )
    conn.commit()

    # Seed solo si está vacío, para poder probar/demostrar sin crear todo a mano
    row = conn.execute("SELECT COUNT(*) AS c FROM veterinario").fetchone()
    if row["c"] == 0:
        vets = [
            (str(uuid.uuid4()), "Dra. Pía Contreras", "general"),
            (str(uuid.uuid4()), "Dr. Marcelo Soto", "felinos"),
        ]
        conn.executemany(
            "INSERT INTO veterinario (id, nombre, especialidad) VALUES (?, ?, ?)", vets
        )

        bloques = []
        for vet_id, _, _ in vets:
            for i in range(3):
                bloques.append(
                    (
                        str(uuid.uuid4()),
                        vet_id,
                        "2026-09-22",
                        f"{9 + i}:00",
                        f"{10 + i}:00",
                        3,
                        3,
                    )
                )
        conn.executemany(
            """INSERT INTO bloque_horario
               (id, id_veterinario, fecha, hora_inicio, hora_fin, cupos_totales, cupos_disponibles)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            bloques,
        )
        conn.commit()
    conn.close()
