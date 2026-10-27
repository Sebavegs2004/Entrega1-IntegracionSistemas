-- ============================================================
-- Esquema del servicio Agenda (fuente de verdad de cupos) en
-- SQLite. Lo ejecuta db.inicializar() al arrancar el servicio.
--
-- SQLite no tiene AUTO_INCREMENT ni tipos DATE: por eso los ids son
-- INTEGER PRIMARY KEY AUTOINCREMENT y la fecha se guarda como texto
-- ('AAAA-MM-DD'), igual que la hora ('HH:MM').
-- Los datos de ejemplo están aparte, en sql/agenda_seed.sql.
-- ============================================================

-- Veterinarios de la clínica
CREATE TABLE IF NOT EXISTS veterinarios (
    id_veterinario INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre         TEXT NOT NULL,
    especialidad   TEXT NOT NULL
);

-- Bloques horarios: un veterinario + fecha + hora con un tope de cupos.
-- "cupos_libres" es el dato que Agenda administra (reservar/liberar).
CREATE TABLE IF NOT EXISTS bloques_horarios (
    id_bloque      INTEGER PRIMARY KEY AUTOINCREMENT,
    id_veterinario INTEGER NOT NULL,
    fecha          TEXT NOT NULL,          -- formato AAAA-MM-DD
    hora_inicio    TEXT NOT NULL,          -- formato HH:MM (texto simple)
    hora_fin       TEXT NOT NULL,
    cupos_totales  INTEGER NOT NULL,
    cupos_libres   INTEGER NOT NULL,
    FOREIGN KEY (id_veterinario) REFERENCES veterinarios (id_veterinario)
);

-- Registro de liberaciones de cupo, claveado por id_reserva.
-- Permite que LiberarCupo sea idempotente: una misma reserva solo
-- libera su cupo una vez, aunque se llame dos veces concurrentemente.
CREATE TABLE IF NOT EXISTS liberaciones_cupos (
    id_reserva    INTEGER PRIMARY KEY,   -- id de la reserva (de Reservas)
    id_bloque     INTEGER NOT NULL,      -- bloque al que pertenece
    liberado_en   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_bloque) REFERENCES bloques_horarios (id_bloque)
);
