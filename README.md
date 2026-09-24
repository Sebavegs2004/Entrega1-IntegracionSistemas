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

## Pruebas de contrato (OpenAPI + proto)

Verifican automáticamente que la implementación cumple **ambos contratos**:

- `tests/test_openapi.py` — contrato **REST**:
  - La spec `contracts/openapi.yaml` es un OpenAPI 3.0 válido.
  - Cada endpoint documentado existe en la API viva (cobertura spec → implementación).
  - Cada cuerpo de respuesta (éxitos **y** errores) valida contra el schema declarado
    (`jsonschema`, con `$ref` internos resueltos).
  - Flujo E2E: crear dueño → listar bloques (desde Agenda vía gRPC) → reservar →
    verificar que el cupo bajó → cancelar (204) → verificar que el cupo volvió.
- `tests/test_proto.py` — contrato **gRPC**:
  - `agenda.proto` compila y su descriptor expone exactamente los 4 RPC.
  - Los 4 métodos responden como dicta el contrato (incluye `NOT_FOUND`,
    `SIN_CUPO` y casos límite de liberar cupos).

Cómo correrlas (dentro de la red Docker, con la pila arriba):

```bash
docker compose up --build -d
docker compose --profile tests build
docker compose --profile tests run --rm tests
```

Solo los tests REST desde el host (requiere las dependencias de
`tests/requirements.txt` instaladas localmente):

```bash
API_BASE=http://localhost:5000 pytest tests/test_openapi.py
```

> El caso 503 (Agenda caída) no forma parte del suite automático: forzarlo
> requiere apagar el servicio Agenda, y en una pila sana no ocurre.
> `tests/` y el servicio de compose permiten revisarlo manualmente si se desea.

## Segundo cliente gRPC (.NET) — interoperabilidad

Para evidenciar que el contrato `agenda.proto` no está acoplado a Python,
hay un **cliente C#** (`cliente-dotnet/`) que consume el **mismo servicio
Agenda Python** a partir del **mismo `.proto`**. Ningún lado sabe en qué
lenguaje está el otro: lo único compartido es el contrato.

- `cliente-dotnet/ClienteAgenda.csproj` — `Grpc.Tools` compila
  `contracts/agenda.proto` a C# automáticamente en el `dotnet build`
  (a diferencia de Python, no hay `protoc` manual).
- `cliente-dotnet/Program.cs` — demo Unary que llama a los 4 RPC:
  `ListarBloques` (con y sin filtros), `ConsultarVeterinario` (incluye el
  manejo de `NOT_FOUND`, el mismo código de estado que ve el cliente Python)
  y el ciclo `ReservarCupo` + `LiberarCupo` para demostrar la escritura
  interoperable sin dejar la base modificada.

Cómo correrlo (dentro de la red Docker, con Agenda arriba):

```bash
docker compose up -d
docker compose --profile cliente build
docker compose --profile cliente run --rm cliente-dotnet
```

> `bin/` y `obj/` (las DLLs que verías en __cualquier__ proyecto .NET) son
> artefactos de build generados por `dotnet`; no se versionan (ver `.gitignore`).

## Primer cliente gRPC (Python) — contracara para comparar

`cliente-python/` es el mismo demo en Python sobre el mismo contrato y el
mismo servidor. La salida es deliberadamente **equivalente** a la del
cliente .NET (mismas secciones, mismo formato), para que la interoperabilidad
se vea comparando los dos outputs lado a lado.

```bash
docker compose --profile cliente build
docker compose --profile cliente run --rm cliente-python   # y/o ...
docker compose --profile cliente run --rm cliente-dotnet
```

Los stubs los regenera `grpc_tools.protoc` en el `Dockerfile` de cada cliente
(igual que en `agenda/`), así que ninguno de los dos clientes lleva código
"traducido" a mano: los dos compilan el mismo `contracts/agenda.proto`.

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
cliente-dotnet/      segundo cliente gRPC (.NET) — interoperabilidad
cliente-python/      primer cliente gRPC (Python) — contracara para comparar
tests/               pruebas de contrato (test_openapi.py + test_proto.py)
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