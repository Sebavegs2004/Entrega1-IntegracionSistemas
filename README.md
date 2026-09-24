# Sistema de Gestión de Clínica Veterinaria — VidaAnimal

MVP de integración entre **Reservas** (API REST + interfaz web) y
**Agenda** (servicio interno gRPC), con **MySQL** y **Docker**.

```
┌──────────────┐   gRPC (Unary)   ┌──────────────┐
│   Reservas   │ ───────────────▶ │    Agenda    │
│  Flask + UI  │                  │   gRPC (py)  │
│  (puerto 5000)│                  │   (interno)  │
└──────┬───────┘                  └──────┬───────┘
       │ MySQL (reservas_db)             │ MySQL (agenda_db)
```

Cada servicio tiene **su propia base de datos**; la integración entre
ellos ocurre solo por gRPC.

## Cómo levantar todo

```bash
docker compose up --build
```

| Servicio          | Acceso                          |
|-------------------|---------------------------------|
| Interfaz web + API| http://localhost:5000           |
| Swagger UI        | http://localhost:5000/swagger   |
| Spec OpenAPI      | http://localhost:5000/openapi.yaml |
| Agenda (gRPC)     | solo dentro de la red de Docker |

Para probar los endpoints desde Swagger UI, usa el botón **Authorize**
y pega la clave `clave-secreta-vet-2026` (se envía como header `X-API-Key`).

> `sql/*.sql` se ejecutan la primera vez que se crean los volúmenes.
> Para volver a los datos de ejemplo: `docker compose down -v` y levantar de nuevo.

## Probar la API

```bash
# Crear un dueño
curl -X POST http://localhost:5000/v1/duenos \
  -H "X-API-Key: clave-secreta-vet-2026" -H "Content-Type: application/json" \
  -d '{"nombre":"Juan Pérez","telefono":"+56912345678"}'

# Ver bloques disponibles (vienen de Agenda vía gRPC)
curl http://localhost:5000/v1/bloques -H "X-API-Key: clave-secreta-vet-2026"

# Crear una reserva (id_bloque de la lista anterior)
curl -X POST http://localhost:5000/v1/reservas \
  -H "X-API-Key: clave-secreta-vet-2026" -H "Content-Type: application/json" \
  -d '{"id_dueno":1,"id_bloque":1,"mascota_nombre":"Rex","motivo":"Control anual"}'

# Listar reservas
curl http://localhost:5000/v1/reservas -H "X-API-Key: clave-secreta-vet-2026"

# Cancelar una reserva (libera el cupo en Agenda)
curl -X DELETE http://localhost:5000/v1/reservas/1 -H "X-API-Key: clave-secreta-vet-2026"
```

## Estructura

```
contracts/           agenda.proto + openapi.yaml (fuente única de verdad)
sql/                 scripts .sql que crean las tablas (datos de ejemplo)
agenda/              servicio gRPC (Python) + su cliente stub
reservas/            servicio Flask (API + interfaz web Bootstrap 5)
  templates/index.html
  static/styles.css, static/app.js
docker-compose.yml   levanta todo con un solo comando
generar_stubs.sh     regenera los stubs de gRPC (opcional, solo local)
```

## Decisiones técnicas (resumen para la defensa)

**¿Por qué gRPC Unary?** Cada operación son consultas o actualizaciones
puntuales (consultar veterinario, listar bloques, reservar/liberar cupo):
el cliente envía un mensaje y recibe una única respuesta. El modo *Unary*
es el más simple de gRPC y no se necesita streaming de datos.

**¿Por qué API Key?** Es la autenticación más sencilla de implementar y
explicar: cada petición lleva la clave en el header `X-API-Key` y un
decorador de Flask la valida. No requiere sesiones ni tokens. (En un
sistema real se usaría algo más robusto, pero cumple el requisito.)

**¿Cómo se maneja la caída de Agenda?** El cliente gRPC usa un timeout
de 3 segundos. Si Agenda no responde, se lanza `AgendaNoDisponibleError`
y la API responde **HTTP 503** con un JSON amigable:
`{"error": "AGENDA_NO_DISPONIBLE", "detalle": "..."}`. La reserva NO se
inserta: el cupo primero se asegura en Agenda y recién después se guarda.

**¿Por qué "copias" de datos en Reservas?** En la tabla `reservas` se
guarda una copia de la cita (vet, fecha, hora) que devuelve Agenda.
Así la interfaz puede mostrar las reservas sin tener que llamar a
Agenda en cada consulta. La fuente de verdad del cupo sigue siendo Agenda.

## Seguridad y pendientes (nota honesta)

- La API Key viaja también en el JavaScript de la interfaz: aceptable
  para un MVP de laboratorio, inviable en producción (allí el navegador
  usaría sesión/token).
- Sin pruebas automáticas ni replicación; los cupos se descuentan con
  un `UPDATE ... WHERE cupos_libres > 0` que evita vender más cupos de
  los disponibles en operaciones simultáneas de un solo proceso.