# Sistema de Gestión de Clínica Veterinaria — VidaAnimal

MVP de integración entre **Reservas** (API REST + interfaz web) y
**Agenda** (servicio interno gRPC), con **SQLite**, **Redis** y
**Docker**.

```
┌──────────────┐   gRPC (Unary)   ┌──────────────┐
│   Reservas   │ ───────────────▶ │    Agenda    │
│  Flask + UI  │                  │   gRPC (py)  │
│  (puerto 5000)│                  │   (interno)  │
└──────┬───────┘                  └──────┬───────┘
       │ SQLite: reservas.db              │ SQLite: agenda.db
       │                                  │
       │  caché + idempotencia            │
       └──────────────▶ ┌──────────────┐  │
                       │  Redis       │  │
                       │ (contenedor) │◀─┘
                       └──────────────┘
```

Cada servicio tiene **su propia base de datos**; la integración entre
ellos ocurre solo por gRPC. Las dos bases son **archivos SQLite**
guardados en volúmenes de Docker, así que no hay servidores de base
de datos que instalar ni mantener. Redis es un **tercer
contenedor**, pero no es una base de datos: es una caché en memoria
que se puede borrar sin perder nada (ver *Idempotencia y caché* más
abajo).

## Cómo levantar todo

```bash
docker compose up --build
```

Eso es todo: el proyecto **solo corre en Docker**, no hay modo local.
No se instala nada en el computador, no hay que levantar una base de
datos y los archivos SQLite viven dentro de los volúmenes.

| Servicio          | Acceso                          |
|-------------------|---------------------------------|
| Interfaz web + API| http://localhost:5000           |
| Swagger UI        | http://localhost:5000/v1/docs   |
| Agenda (gRPC)     | solo dentro de la red de Docker |
| Redis (caché)     | solo dentro de la red de Docker |

Lo único publicado hacia el host es el puerto 5000: Agenda y Redis se
usan por nombre de servicio, desde la red de Docker.

La especificación OpenAPI no se publica en ninguna ruta: es el archivo
`contracts/openapi.yaml`, y Swagger UI la lee y la muestra en `/v1/docs`.

Para probar los endpoints desde Swagger UI, usa el botón **Authorize**
y pega la clave `clave-secreta-vet-2026` (se envía como header `X-API-Key`).

También hay una **colección de Postman** con las pruebas de la API
(`postman/VidaAnimal_Reservas.postman_collection.json`), por si quieres
probarla sin escribir nada: impórtala en la app de Postman con
*Import → Link/Text/File*. Cubre 200, 201, 204, 400, 401, 404, 405,
409, 415 y 503, y son **32 peticiones con 137 aserciones**.

Las pruebas se pasan datos de una a otra (la 201 de dueños guarda
`id_dueno`, la 201 de bloques guarda `id_bloque` por disponibilidad y
la 201 de reservas guarda `id_reserva`), así que **el orden importa**.
Para que pasen las 137 aserciones hay que correr la colección en
**tres pasos**, porque la carpeta 6 necesita Agenda apagado y la
carpeta 7 necesita Agenda encendido:

```bash
docker compose down -v && docker compose up --build   # desde datos limpios
```

| Paso | Qué hacer | Por qué |
|---|---|---|
| 1 | En Postman, correr las carpetas **0 a 5** | Agenda está arriba: dan 200/201/400/401/404/405/409/415 |
| 2 | `docker compose stop agenda`, poner `agenda_caida` en `si` y correr la **carpeta 6** | con Agenda abajo, las tres rutas que dependen de él dan 503 |
| 3 | `docker compose start agenda` y correr la **carpeta 7** | la cancelación necesita Agenda para liberar el cupo |

> La carpeta 6 se salta sola (sin fallar la corrida) mientras
> `agenda_caida` siga en `no`, así que un **Run** normal sobre la
> colección completa no la rompe: corre 29 peticiones y 124 aserciones.
>
> Ojo con el paso 2: no se puede correr la carpeta 6 encima de una
> corrida anterior, porque su prueba de `DELETE` necesita una reserva
> **activa** y, si ya se canceló, la API responde 409 en vez de 503.
> Por eso la carpeta 6 va antes que la 7.

> La primera vez que arranca, cada servicio crea su archivo SQLite y sus
> tablas (`db.inicializar()`); Agenda además carga los datos de ejemplo
> de `sql/agenda_seed.sql` **solo si la base está vacía**.
> Los archivos viven en los volúmenes `reservas_data` y `agenda_data`,
> así que los datos sobreviven a `docker compose down` y a
> `docker compose up --build`.
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

Todos los errores usan el mismo formato, con un código y un detalle:

```json
{"error": "NO_ENCONTRADO", "detalle": "Recurso no encontrado"}
```

## Estructura

```
contracts/           agenda.proto + openapi.yaml (fuente única de verdad)
sql/                 .sql que db.inicializar() ejecuta al arrancar
  agenda.sql           tablas de Agenda
  agenda_seed.sql      datos de ejemplo (solo si la base está vacía)
  reservas.sql         tablas de Reservas
agenda/              servicio gRPC (Python)
  db.py                 conexión SQLite + inicializar()
  server.py             las 3 operaciones del .proto
reservas/            servicio Flask (API + interfaz web Bootstrap 5)
  app.py                 endpoints, error handlers, Swagger UI
  db.py                 conexión SQLite + inicializar()
  agenda_client.py       cliente gRPC hacia Agenda
  templates/index.html
  static/styles.css, static/app.js
docker-compose.yml   levanta todo con un solo comando
postman/             colección de Postman con las pruebas de la API
  VidaAnimal_Reservas.postman_collection.json
docs/adr/            los cuatro ADR (una decisión por archivo)
  001-dos-servicios-y-base-por-servicio.md
  002-rest-afuera-grpc-adentro.md
  003-versionado-y-evolucion-del-contrato.md
  004-fallos-de-agenda.md
```

## Idempotencia, caché e HATEOAS

Las tres cosas que la API agrega por encima de "guardar y devolver".
Esta tabla dice **dónde está cada una**, porque es lo primero que
pregunta alguien que revisa el código:

| Qué | Dónde está implementado | Para qué sirve |
|---|---|---|
| **Idempotencia** | `reservas/app.py` → `crear_reserva()` (lee la clave) + `leer_reserva_idempotente()` / `guardar_reserva_idempotente()` | que repetir la misma petición no cree dos reservas |
| **Caché** | `reservas/app.py` → `leer_bloques_cacheados()` / `guardar_bloques_cacheados()` / `olvidar_bloques()`, en `listar_bloques()` | no preguntar a Agenda en cada lectura de disponibilidad |
| **HATEOAS** | `reservas/app.py` → `obtener_reserva()` (arma el diccionario `_links`) | que la respuesta diga qué se puede hacer después, sin URLs adivinadas |

### Idempotencia — la cabecera `Idempotency-Key`

**El problema.** `POST /v1/reservas` no es seguro de repetir: si el
cliente manda la petición, la red se cae antes de recibir la respuesta,
y el cliente la reintenta, se crea **una reserva duplicada** y un cupo
descontado de más. Un `POST` que crea un recurso es por definición
repetible, y sin ayuda no hay forma de que el servidor distinga "el
cliente no sabe si salió" de "el cliente quiere otra reserva".

**La solución.** El cliente manda una clave única en la cabecera
`Idempotency-Key`. La API guarda en Redis la reserva que creó con esa
clave, y si llega la misma clave otra vez, **devuelve la que ya
tenía** en vez de crear otra:

```bash
# Las dos peticiones son idénticas, con la misma clave
curl -X POST http://localhost:5000/v1/reservas \
  -H "X-API-Key: clave-secreta-vet-2026" -H "Content-Type: application/json" \
  -H "Idempotency-Key: turno-123" \
  -d '{"id_dueno":1,"id_bloque":1,"mascota_nombre":"Rex","motivo":"Control"}'
# → 201 {"id_reserva": 1, ...}

# repetida: mismo cuerpo, misma clave
# → 200 {"id_reserva": 1, ...}   la MISMA reserva, no una nueva
```

El código es el orden de `crear_reserva()`: primero mira la clave
(`repetida = leer_reserva_idempotente(clave)`) y, si encuentra algo,
sale con `200`; si no, sigue el camino normal y al final guarda la
respuesta con `guardar_reserva_idempotente(clave, reserva)`.

**Por qué importa acá.** Es lo que hace **reintentable el 503**. Cuando
Agenda está caído, la API responde 503 y el cliente puede reintentar
con la misma `Idempotency-Key`: si a la segunda vez Agenda ya
respondió, se crea la reserva; si la primera vez *sí* se había creado
pero se perdió la respuesta, la segunda devuelve la misma. Sin
idempotencia, el 503 documentado en ADR-004 sería una invitación a
duplicar reservas.

**El detalle honesto.** Vive en Redis, no en la base de datos: si el
contenedor de Redis se reinicia, se pierden las claves y la protección
con ellas (la base SQLite de reservas sigue intacta). Es la decisión
correcta para un MVP, pero en producción esto se guardaría en la base,
que es lo que sobrevive a los reinicios.

### Caché con Redis — `GET /v1/bloques`

**El problema.** `/v1/bloques` es la lectura más repetida del sistema:
la web la llama al cargar, y cada llamada tiene que ir a Agenda por
gRPC para volver con la misma lista. Es un gasto de red y de CPU para
un dato que cambia una o dos veces por minuto.

**La solución.** La respuesta se guarda en Redis con una vida de 60
segundos (`TTL_BLOQUES`). La segunda lectura dentro de ese minuto se
resuelve **sin tocar Agenda**.

**La parte importante: cuándo se borra.** Una caché que no se
invalida muestra cupos que ya se gastaron, y eso en una clínica es
justo el error que no se puede cometer. Por eso la lista se borra
explícitamente en las dos operaciones que cambian un cupo:

- `crear_reserva()` llama a `olvidar_bloques()` cuando asegura el cupo.
- `cancelar_reserva()` también, cuando lo libera.

Y el TTL de 60 segundos es el respaldo: aunque algún camino olvidara
borrarla, lo peor que pasa es que la información se refresque sola al
cabo de un minuto.

**Lo que la caché NO hace.** `POST /v1/reservas` **nunca** lee de la
caché para decidir si hay cupo: el cupo se asegura siempre llamando a
`reservar_cupo()` en Agenda. La caché es solo para *mostrar*
disponibilidad; la fuente de verdad de un cupo sigue siendo Agenda.

### HATEOAS — el campo `_links`

**El problema.** Un cliente que recibe `{"id_reserva": 1}` tiene que
*adivinar* que puede pedir `/v1/reservas/1` o borrar `/v1/reservas/1`.
Si mañana cambia el diseño de las URLs, hay que ir a cambiar el
cliente aunque la respuesta del servidor sea idéntica.

**La solución.** La respuesta trae las acciones disponibles dentro del
propio recurso. `GET /v1/reservas/1` devuelve:

```json
{
  "id_reserva": 1,
  "estado": "activa",
  "_links": {
    "self": "/v1/reservas/1",
    "dueno": "/v1/reservas/1"→"/v1/duenos/1",
    "cancelar": { "href": "/v1/reservas/1", "metodo": "DELETE" }
  }
}
```

Está en `obtener_reserva()`: arma el diccionario `_links` con `self` y
`dueno` siempre, y agrega `cancelar` **solo si la reserva sigue
activa** (`if datos["estado"] != "cancelada"`). O sea, el servidor
publica el estado real: una reserva cancelada no ofrece la acción de
cancelar, porque no tiene sentido.

**Para qué sirve en la práctica.** El cliente sigue la respuesta en vez
de construir URLs: no hardcodea `/v1/reservas/1` ni `/v1/duenos/1`, y
si la API cambia de rutas, el cliente se entera solo leyendo `_links`.
Además el enlace a `dueno` hace que "ver los datos de esta reserva" y
"ver a su dueño" sean un solo clic, sin que el cliente tenga que saber
que el dueño vive en otro recurso.

## Requisitos opcionales: qué quedó implementado

Además de lo básico, hay cinco mejoras opcionales: tres quedaron
implementadas, una a medias y una no se hizo. La tabla dice el estado de
cada una y dónde se puede ver en el código, para no tener que buscarlas:

| # | Mejora | Estado | Dónde está |
|---|---|---|---|
| **O1** | **Caché con Redis**, con invalidación al reservar o liberar | **Implementada** | `reservas/app.py` → `leer_bloques_cacheados()`, `guardar_bloques_cacheados()`, `olvidar_bloques()`, usadas en `listar_bloques()`, `crear_reserva()` y `cancelar_reserva()`. Redis corre como servicio `redis_cache` en Docker. Detalle en *Caché con Redis* más abajo. |
| **O2** | **Idempotencia** con la cabecera `Idempotency-Key` | **Implementada** | `reservas/app.py` → `crear_reserva()` lee la cabecera y consulta `leer_reserva_idempotente()`; si la clave ya se usó, responde `200` con la reserva ya creada. Se guarda con `guardar_reserva_idempotente()`. Detalle en *Idempotencia* más abajo. |
| **O3** | **HATEOAS** con enlaces según el estado | **Implementada** | `reservas/app.py` → `obtener_reserva()` arma `_links` con `self` y `dueno`, y agrega `cancelar` (con su `metodo`) solo si la reserva sigue activa. El schema `_links` está declarado en `contracts/openapi.yaml`. Detalle en *HATEOAS* más abajo. |
| **O4** | **Pruebas de contrato** que verifiquen el OpenAPI y el `.proto` | **Parcial** | La validez del OpenAPI se comprueba con un contenedor efímero que corre `openapi-spec-validator` (ver *Qué se verificó*), y la carpeta 0 de la colección de Postman compara la especificación servida en `/v1/docs` con las rutas reales, los nombres de los schemas de error y el header de autenticación. No hay, en cambio, una suite que valide el `.proto` ni que verifique el contrato de forma continua en cada build. |
| **O5** | **Segundo cliente gRPC** en otro lenguaje | **No implementada** | Todo el consumo de Agenda es desde Python (`reservas/agenda_client.py`). Se descartó por alcance: el `.proto` ya genera stubs para cualquier lenguaje, y agregar un cliente .NET sin uso real no agregaba valor al sistema. |

## Decisiones técnicas (resumen para la defensa)

**¿Por qué gRPC Unary?** Las tres operaciones del `.proto` (listar
bloques, reservar cupo, liberar cupo) son consultas o actualizaciones
puntuales: el cliente envía un mensaje y recibe una única respuesta. El
modo *Unary* es el más simple de gRPC y no se necesita streaming de
datos.

**¿Por qué SQLite?** Es una base de datos **basada en un archivo**: no
hay servidor, ni usuarios, ni contraseñas, ni puertos. Para un MVP de
laboratorio es la opción más simple de instalar y de defender, y cada
servicio mantiene su propio archivo (además, SQLite **no** permite que
dos servicios compartan archivos con escritura simultánea, así que cada
uno tiene el suyo). La conexión se configura con una sola variable de
entorno, `DB_PATH`.

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

**¿Por qué un solo esquema de error en OpenAPI?** Todos los errores de
la API tienen la misma forma (`{"error", "detalle"}`), así que la
especificación define un único schema `Error` y cada respuesta apunta a
él con un `$ref`. Además, un mismo código HTTP puede ocurrir por motivos
distintos (por ejemplo, un 404 puede ser un dueño que no existe, una
reserva que no existe o una ruta mal escrita), por eso el texto del
error es general y no menciona un recurso en particular.

**¿Cómo se evita repetir los errores?** Cada código HTTP está escrito una
sola vez, en su manejador global de `reservas/app.py` (`404`, `405`,
`415`, `500`, `503`). Las rutas no construyen el JSON: solo llaman a
`abort(codigo)`, que lanza el error y Flask encamina la respuesta por el
manejador. Así un `abort(404)` desde `obtener_reserva` y una URL mal
escrita producen exactamente el mismo cuerpo, sin que las rutas repitan
el mensaje.

## Seguridad y pendientes (nota honesta)

- La API Key viaja también en el JavaScript de la interfaz: aceptable
  para un MVP de laboratorio, inviable en producción (allí el navegador
  usaría sesión/token).
- La base es un archivo en un volumen de Docker: convenientemente
  ignorado por `.gitignore` (`data/`, `*.db`), pero sin cifrado ni
  control de acceso más allá del del servidor.
- Sin pruebas de contrato automáticas contra el `.proto`: las
  pruebas están en la colección de Postman
  (`postman/VidaAnimal_Reservas.postman_collection.json`: 32 peticiones y
  137 aserciones que cubren 200, 201, 204, 400, 401, 404, 405, 409, 415
  y 503) y verifican el comportamiento de la API, no el cumplimiento
  del OpenAPI ni del `.proto`; los cupos se descuentan con
  un `UPDATE ... WHERE cupos_libres > 0` que evita vender más cupos de
  los disponibles en operaciones simultáneas de un solo proceso.

## Declaración de uso de asistentes de IA

El curso permite el uso de asistentes de IA con una condición: que se
declare en el README qué se usó, para qué y qué se verificó. Esta es esa
declaración.

**Herramienta.** OpenCode, un asistente de código con el que se
conversó por texto. No se usó ningún otro asistente, ni para el código ni
para el informe.

**Qué se usó para.** La base del proyecto (el `.proto`, los servicios Flask
y gRPC, la interfaz web y el esquema MySQL original) la escribieron los
integrantes. El asistente se usó en la etapa final, sobre esos cimientos,
para lo siguiente:

| Tarea | Qué hizo concretamente |
|---|---|
| Migración de MySQL a SQLite | Reescribir `reservas/db.py` y `agenda/db.py` con `sqlite3`, crear `sql/*.sql` (esquema y datos de ejemplo), quitar `mysql-connector-python`, actualizar `docker-compose.yml` (volúmenes en vez de servidores de base) y los Dockerfiles |
| Limpieza de `reservas/app.py` | Unificar los códigos de error en uno por estado HTTP, agregar el manejador de 415, documentar las funciones, dejar el manejo de Agenda en un solo camino y sacar los `if` de validación a mano: los cuerpos se validan con modelos de Pydantic (`reservas/app.py`) |
| Contrato OpenAPI | Reescribir `contracts/openapi.yaml`: declarar los cuerpos de las peticiones como schemas (`NuevoDueno`, `NuevaReserva`), un schema de error por código HTTP (`Error400`, `Error401`, `Error404`, `Error409`, `Error415`, `Error503`) y generalizar el 404 a "recurso no encontrado" |
| Ruta de la documentación | Swagger UI en `/v1/docs`, que lee `contracts/openapi.yaml` y lo muestra embebido: se eliminó la ruta `/openapi.yaml` y con ella la segunda copia del contrato |
| Rutas de archivos | Dejar el código con una sola ruta de trabajo: el proyecto es 100 % Docker y no quedó ninguna opción de ejecución local |
| Pruebas | Generar la colección de Postman con sus aserciones por estado HTTP |
| Documentación | Redactar los cuatro ADR de `docs/adr/` y esta declaración |

**Qué NO hizo el asistente, y es del equipo.** El contrato `.proto`, el
experimento de la Competencia 6 (con su diseño, las mediciones y las
conclusiones), el informe, el video y la decisión de qué alternativas
descartar en cada ADR: eso se fundamentó y se escribió en el equipo. Del
mismo modo, **ningún integrante puede decir que no revisó** el código que
el asistente escribió: la defensa pregunta por cualquier línea.

**Qué se verificó, y cómo se repite.** Cada cambio se comprobó contra los
contenedores reales, no solo por lectura:

| Verificación | Cómo se reproduce |
|---|---|
| El sistema completo levanta y queda healthy | `docker compose up --build` |
| Los datos sobreviven a `down` y a `up --build` | `docker compose down && docker compose up --build` |
| Los diez estados HTTP de la API | La colección de Postman, carpeta por carpeta (137 aserciones) |
| El modo de falla (T7): con Agenda detenido las tres rutas que dependen de él responden 503 | `docker compose stop agenda`, poner `agenda_caida` en `si` y correr la carpeta 6 |
| La idempotencia: repetir la misma `Idempotency-Key` devuelve la misma reserva y no crea otra | Carpeta 4 de la colección |
| El contrato es un OpenAPI válido | Un contenedor efímero valida el `openapi.yaml` sin instalar nada en el host (ver abajo) |
| El contrato sigue describiendo la API real | La prueba de la carpeta 0, que compara la especificación embebida en `/v1/docs` con las rutas reales |
| La base de datos por servicio | Un archivo por servicio, en volúmenes separados, sin referencias cruzadas entre bases |

El validador del OpenAPI también corre en Docker, así que tampoco exige
tener nada instalado en el computador:

```bash
docker run --rm -v "$PWD/contracts:/contrato:ro" python:3.12-slim \
  sh -c "pip install --quiet openapi-spec-validator && openapi-spec-validator /contrato/openapi.yaml"
# → /contrato/openapi.yaml: OK
```

La colección de Postman es una sugerencia para quien quiera probarla sin
escribir nada: se importa en la app de Postman
(*Import → Link/Text/File*) y se corre con *Run* sobre la colección.
