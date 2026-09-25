-- ============================================================
-- Datos de ejemplo (seed) del servicio Agenda.
-- db.inicializar() ejecuta este archivo SOLO cuando la base está
-- vacía, por eso los datos se cargan una vez y no se repiten
-- cada vez que se reconstruye el contenedor.
--
-- Hay bloques con cupos libres, casi llenos y agotados
-- (cupos_libres = 0) para poder probar los casos de la API.
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
