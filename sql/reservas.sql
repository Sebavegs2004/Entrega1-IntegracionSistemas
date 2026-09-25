-- ============================================================
-- Esquema del servicio Reservas (API pública + interfaz web)
-- en SQLite. Lo ejecuta db.inicializar() al arrancar el servicio.
--
-- NOTA: Aquí NO se guardan los veterinarios ni los bloques: esos
-- datos son de Agenda (fuente de verdad). En reservas solo guardamos
-- una COPIA (número de bloque y los datos de la cita) para poder
-- mostrar las reservas en la interfaz sin llamar a Agenda.
--
-- SQLite no tiene AUTO_INCREMENT ni tipos DATE: por eso los ids son
-- INTEGER PRIMARY KEY AUTOINCREMENT y las fechas se guardan como
-- texto ('AAAA-MM-DD' y 'AAAA-MM-DD HH:MM:SS').
-- ============================================================

-- Dueños de las mascotas
CREATE TABLE IF NOT EXISTS duenos (
    id_dueno INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre   TEXT NOT NULL,
    telefono TEXT NOT NULL,
    email    TEXT
);

-- Reservas: id_bloque hace referencia a Agenda, pero no hay FK
-- porque cada servicio tiene su propia base de datos.
CREATE TABLE IF NOT EXISTS reservas (
    id_reserva         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_dueno           INTEGER NOT NULL,   -- dueño (FK a duenos de esta base)
    id_bloque          INTEGER NOT NULL,   -- id en la base de datos de Agenda
    nombre_veterinario TEXT NOT NULL,      -- copia para mostrar
    fecha              TEXT NOT NULL,      -- copia para mostrar (AAAA-MM-DD)
    hora_inicio        TEXT NOT NULL,      -- copia para mostrar (HH:MM)
    mascota_nombre     TEXT NOT NULL,
    motivo             TEXT,
    estado             TEXT NOT NULL DEFAULT 'activa',  -- 'activa' | 'cancelada'
    creada_en          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_dueno) REFERENCES duenos (id_dueno)
);
