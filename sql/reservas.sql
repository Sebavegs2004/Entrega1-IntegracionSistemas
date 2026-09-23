-- ============================================================
-- Base de datos del servicio Reservas (API pública + interfaz web).
-- Este archivo lo ejecuta MySQL la primera vez que se crea el
-- contenedor (docker-entrypoint-initdb.d).
--
-- NOTA: Aquí NO se guardan los veterinarios ni los bloques: esos
-- datos son de Agenda (fuente de verdad). En reservas solo guardamos
-- una COPIA (número de bloque y los datos de la cita) para poder
-- mostrar las reservas en la interfaz sin llamar a Agenda.
-- ============================================================
CREATE DATABASE IF NOT EXISTS reservas_db;
USE reservas_db;

-- Dueños de las mascotas
CREATE TABLE duenos (
    id_dueno INT AUTO_INCREMENT PRIMARY KEY,
    nombre   VARCHAR(100) NOT NULL,
    telefono VARCHAR(30)  NOT NULL,
    email    VARCHAR(120)
);

-- Reservas: id_bloque hace referencia a Agenda, pero no hay FK
-- porque cada servicio tiene su propia base de datos.
CREATE TABLE reservas (
    id_reserva          INT AUTO_INCREMENT PRIMARY KEY,
    id_dueno            INT NOT NULL,
    id_bloque           INT NOT NULL,              -- id en la BD de Agenda
    nombre_veterinario  VARCHAR(100) NOT NULL,     -- copia para mostrar
    fecha               DATE NOT NULL,             -- copia para mostrar
    hora_inicio         VARCHAR(5) NOT NULL,       -- copia para mostrar
    mascota_nombre      VARCHAR(100) NOT NULL,
    motivo              VARCHAR(200),
    estado              VARCHAR(10) NOT NULL DEFAULT 'activa',  -- 'activa' | 'cancelada'
    creada_en           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_dueno) REFERENCES duenos (id_dueno)
);