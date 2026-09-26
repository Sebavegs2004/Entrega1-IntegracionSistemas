# ADR-004 · Qué responde la API cuando Agenda no está

Estado: aceptada
Responde a: D4 (resiliencia y modos de falla) · T7 (manejo de fallas de la dependencia)

## Contexto

Ninguna reserva se registra sin que Agenda confirme que hay cupo. Agenda
es una dependencia externa a la que no controlamos: se puede apagar,
puede reiniciarse o puede quedar lento. La API es la única puerta de
entrada, así que es ella la que tiene que decidir qué le contesta al
usuario cuando la dependencia no responde.

Además, la respuesta importa más allá de este sistema: la API es la
frontera pública y su código de estado es lo que un cliente externo usa
para decidir si reintenta o si cambia de estrategia.

## Alternativas consideradas

- **Opción A — Esperar sin límite.** Es lo más simple de implementar.
  Cuesta que el usuario queda colgado con la petición abierta, y si
  Agenda está colgado se arrastran los hilos del servidor: la API se
  cae por una dependencia que no es suya.
- **Opción B — Cortar con un timeout corto y responder 503.** Obliga a
  decidir y a devolver un error entendible. Cuesta que el usuario no
  logra su objetivo en ese intento: la reserva no se crea.
- **Opción C — Responder "hay cupo" desde la caché y seguir como si
  nada.** Mantiene la disponibilidad para el usuario. Cuesta que es
  mentirle: se vendería un cupo que Agenda no confirmó y, cuando la
  dependencia volviera, la sobreventa aparecería sola. Es exactamente el
  problema que el sistema viene a resolver (sobrecupos), así que la
  descartamos.
- **Opción D — Cortar con timeout y seguir validando por nuestra cuenta.**
  Ofrece no depender de la red en la validación. Cuesta que inventaría
  un segundo conteo de cupos que se desincroniza del real.

## Decisión

Timeout de **3 segundos** en cada llamada gRPC. Si se supera, o si la
llamada falla por cualquier otro motivo, el cliente lanza
`AgendaNoDisponibleError` y la API responde:

```
HTTP 503 Service Unavailable
{"error": "AGENDA_NO_DISPONIBLE", "detalle": "El servicio de Agenda no está disponible. Intenta de nuevo en un momento."}
```

Además, **la reserva no se inserta**: el cupo se asegura en Agenda antes
de escribir en la base de Reservas, así que un fallo de Agenda no deja
reservas fantasma.

## Justificación

Elegimos la Opción B porque distingue los dos casos que de verdad
importan. Un **503** dice "el problema no soy yo, reintenta": es
semánticamente reintentable, y como la creación de reservas es
idempotente (con `Idempotency-Key`), el reintento del cliente no duplica
nada. Un **500** diría "hay un error mío" y el usuario no debería
reintentar. La diferencia no es cosmética: es la que le permite a un
cliente decidir qué hacer.

El timeout de 3 segundos es corto para una operación que es un `SELECT`
o un `UPDATE` contra la base del propio servicio, pero suficiente para no
cortar una llamada sana. Y, como el orden es "primero Agenda, después la
base propia", un fallo de Agenda es el peor caso barato: no se escribe
nada en nuestra base, así que no hay que deshacer.

**Lo que medimos, con sus límites.** Con el contenedor de Agenda
detenido (`docker compose stop agenda`), la conexión se rechaza de
inmediato y el 503 sale en décimas de milisegundo: la colección de Postman
registró `/v1/bloques` en ~40 ms, `POST /v1/reservas` en ~33 ms y
`DELETE /v1/reservas/{id}` en ~154 ms. Son mediciones puntuales de una
corrida, no un experimento controlado: sirven para confirmar que el
escenario "Agenda apagado" está cubierto, no para caracterizar el
comportamiento. **El caso que el timeout protege de verdad es Agenda
lento**, no Agenda caído, y ese caso todavía no está medido: es parte del
experimento del informe.

**Por qué la caché salva parte del problema.** `GET /v1/bloques` se
cachea 60 segundos en Redis, así que mientras Agenda esté caído las
lecturas de disponibilidad que ya fueron cacheadas se siguen
respondiendo. Es un fail-safe parcial: el sistema no se cae entero, solo
deja de poder refrescar la información. La caché se borra al reservar y
al liberar, así que nunca muestra un cupo que ya se usó por esta API.

## Costo aceptado

- **El usuario ve un error donde esperaba una reserva.** Es la
  consecuencia directa de no mentirle (Opción C), y la aceptamos.
- **La disponibilidad puede estar desactualizada hasta 60 segundos.**
  Con Agenda caído, `/v1/bloques` puede seguir devolviendo el último
  estado conocido. Aceptamos que es preferible a no responder, y por eso
  la caché tiene TTL corto y se invalida en cada reserva.
- **Cada petición a una dependencia caída espera hasta el timeout.**
  No hay circuit breaker: si llegan muchas peticiones juntas con Agenda
  caído, cada una paga su espera y se acumulan peticiones vivas en el
  servidor hasta que se agotan sus hilos. Con 3 segundos de espera, el
  margen es estrecho. Un circuit breaker o un reintento con backoff sería
  el siguiente paso, y no está implementado.
- **Una ventana de inconsistencia después de asegurar el cupo.** Si el
  `INSERT` de la reserva fallara después de que Agenda descontara el cupo,
  el cupo quedaría descontado sin reserva y nadie lo devolvería
  automáticamente. Hoy esa corrección es manual.

## Consecuencias

- El cliente necesita manejo de errores: un `503` con
  `Idempotency-Key` se puede reintentar sin riesgo de duplicar.
- Si quisiéramos ser más finos, el `503` podría traer un `Retry-After` y
  el cliente podría distinguir "no hay cupo" (`409`) de "no supe si hay
  cupo" (`503`). Hoy el `detalle` es texto para una persona.
- Si Agenda pasara a ser síncrono en el camino crítico completo (por
  ejemplo, si también validara el veterinario), esta misma decisión
  tendría que revisarse: tal vez el timeout tendría que ser más corto.
