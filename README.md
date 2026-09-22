# Sistema de Gestión de Clínica Veterinaria — VidaAnimal

MVP de integración entre **Reservas** (API REST pública) y **Agenda** (servicio interno gRPC).

## Cómo levantar todo

```bash
docker compose up --build
```

- Reservas (REST): http://localhost:5000
- Agenda (gRPC): localhost:50051

## Probar rápido

```bash
# Crear dueño
curl -X POST http://localhost:5000/v1/duenos \
  -H "X-API-Key: clave-secreta-vet-2026" -H "Content-Type: application/json" \
  -d '{"nombre":"Juan Perez","telefono":"+56912345678"}'

# Listar reservas
curl http://localhost:5000/v1/reservas -H "X-API-Key: clave-secreta-vet-2026"
```

Hay veterinarios y bloques horarios precargados (seed) al iniciar Agenda por primera vez —
revisar la tabla `bloque_horario` para obtener un `id_bloque` real y probar `POST /v1/reservas`.

## Estructura

```
contracts/          openapi.yaml + agenda.proto (fuente única de verdad)
agenda/              servicio gRPC (Python, SQLite)
reservas/            servicio REST (Flask, SQLite)
docs/adr/            Architecture Decision Records (D1-D4)
```

## Declaración de uso de IA

Este proyecto usó asistencia de IA (Claude) para: generar el esqueleto inicial de ambos
servicios (Flask + gRPC), el contrato `.proto`/OpenAPI, y el docker-compose. Todo el código
fue revisado y probado por el equipo; cada integrante debe poder explicar cualquier línea
en la defensa oral.

## Pendiente (no incluido en este MVP)

- Redis (O1), Idempotencia (O2), HATEOAS (O3), pruebas de contrato (O4), segundo cliente gRPC (O5)
- Migrar de SQLite a Postgres si el equipo lo prefiere
- ADR completos en `docs/adr/`
- El experimento de la Competencia 6 (medición de latencia con/sin caché, etc.)
