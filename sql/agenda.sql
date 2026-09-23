-- ============================================================
-- Base de datos del servicio Agenda (fuente de verdad de cupos).
-- Este archivo lo ejecuta MySQL la primera vez que se crea el
-- contenedor (docker-entrypoint-initdb.d).
-- ============================================================
CREATE DATABASE IF NOT EXISTS agenda_db;
USE agenda_db;

-- Veterinarios de la clínica
CREATE TABLE veterinarios (
    id_veterinario INT AUTO_INCREMENT PRIMARY KEY,
    nombre         VARCHAR(100) NOT NULL,
    especialidad   VARCHAR(100) NOT NULL
);

-- Bloques horarios: un veterinario + fecha + hora con un tope de cupos.
-- "cupos_libres" es el dato que Agenda administra (reservar/liberar).
CREATE TABLE bloques_horarios (
    id_bloque      INT AUTO_INCREMENT PRIMARY KEY,
    id_veterinario INT NOT NULL,
    fecha          DATE NOT NULL,          -- formato AAAA-MM-DD
    hora_inicio    VARCHAR(5) NOT NULL,    -- formato HH:MM (texto simple)
    hora_fin       VARCHAR(5) NOT NULL,
    cupos_totales  INT NOT NULL,
    cupos_libres   INT NOT NULL,
    FOREIGN KEY (id_veterinario) REFERENCES veterinarios (id_veterinario)
);

-- ============================================================
-- Datos de ejemplo (seed) para probar la integración.
-- Hay bloques con cupos libres, casi llenos y agotados (cupos_libres = 0).
-- ============================================================
INSERT INTO veterinarios (nombre, especialidad) VALUES
    ('Dra. Carmen Rojas',   'Medicina general'),
    ('Dr. Andrés Soto',     'Cirugía y traumatología'),
    ('Dra. Lucía Fuentes',  'Dermatología');

INSERT INTO bloques_horarios (id_veterinario, fecha, hora_inicio, hora_fin, cupos_totales, cupos_libres) VALUES
    (1, '2026-09-23', '09:00', '09:30', 3, 3),
    (1, '2026-09-23', '09:30', '10:00', 3, 2),
    (1, '2026-09-23', '10:00', '10:30', 3, 0),
    (2, '2026-09-23', '16:00', '16:30', 3, 3),
    (2, '2026-09-23', '16:30', '17:00', 3, 1),
    (1, '2026-09-24', '09:00', '09:30', 3, 2),
    (2, '2026-09-24', '10:00', '10:30', 3, 3),
    (3, '2026-09-24', '11:00', '11:30', 2, 2),
    (3, '2026-09-24', '11:30', '12:00', 2, 1),
    (1, '2026-09-25', '09:00', '09:30', 3, 3),
    (2, '2026-09-25', '16:00', '16:30', 3, 2),
    (3, '2026-09-25', '16:30', '17:00', 2, 2),
    (1, '2026-09-28', '09:00', '09:30', 3, 3),
    (2, '2026-09-28', '09:30', '10:00', 3, 3),
    (3, '2026-09-28', '10:00', '10:30', 2, 1),
    (1, '2026-09-29', '09:00', '09:30', 3, 3),
    (2, '2026-09-29', '16:00', '16:30', 3, 2);