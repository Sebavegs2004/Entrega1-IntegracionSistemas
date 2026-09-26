# ADR-001 · Dos servicios con base propia, en vez de un monolito

Estado: aceptada
Responde a: D1 (estilo de integración y descomposición) · T5 (base de datos por servicio)

## Contexto

VidaAnimal tiene dos sistemas que nacieron separados y nunca se hablaron:
**Agenda**, que administra veterinarios y cupos libres por bloque, y
**Reservas**, que registra dueños y horas reservadas. Agenda lo mantiene
otro equipo, que sigue desarrollándolo activamente, y es la fuente de
verdad sobre qué veterinarios atienden y cuántos cupos quedan.

Dos restricciones acotan la decisión: los dos sistemas tienen dueños
distintos, así que ninguno puede reescribir la base del otro; y la
disponibilidad se consulta "con muchísima frecuencia", así que el camino
de esa consulta es el más caliente del sistema.

## Alternativas consideradas

- **Opción A — Monolito**: un solo servicio y una sola base con las tablas
  de ambos dominios. Ofrece transacciones simples entre dueño, reserva y
  cupo, y un solo despliegue. Cuesta que el equipo de Agenda deja de
  tener su sistema propio, la frontera desaparece dentro del código y las
  dos bases quedan mezcladas en un solo almacén.
- **Opción B — Un servicio que consulta la base de Agenda directamente**
  (base compartida). Es lo más rápido y simple de implementar. Cuesta que
  ambos servicios quedan atados al esquema interno del otro: un cambio en
  la tabla de cupos rompe a Reservas, y deja de haber dos almacenes
  separados.
- **Opción C — Dos servicios, cada uno con su base, comunicados por gRPC.**
  Es la elegida.

## Decisión

Agenda y Reservas son dos servicios independientes, cada uno con su propia
base de datos, y la única forma de que se comuniquen es el contrato
gRPC del `.proto`. La frontera se justifica porque cada sistema tiene
un dueño distinto y un propósito distinto.

## Justificación

La frontera no es arbitraria: son dos contextos delimitados distintos.
Agenda responde "¿hay cupo en este bloque?" y su dueño es otro equipo.
Reservas responde "¿quién es este dueño y qué citas tiene?". La
frecuencia de uso también difiere, y eso justifica una dependencia
declarada y vigilada (con timeout y caché) en vez de una llamada
implícita a una tabla ajena.

Elegimos la Opción C porque es la única que mantiene un almacén por
servicio sin atar a los dos equipos, y porque hace que la dependencia sea
visible en el código (un cliente gRPC explícito) en vez de estar escondida
en un `JOIN` a otra base.

**Duplicación deliberada.** La tabla `reservas` guarda una copia de
`nombre_veterinario`, `fecha` y `hora_inicio` que copiamos de la respuesta
de Agenda. Se duplica a propósito para poder listar reservas sin llamar a
Agenda en cada consulta: las reservas se leen mucho más que lo que se
reservan, y así la pantalla de reservas no depende de que Agenda esté
vivo. El costo explícito está en "Costo aceptado".

## Costo aceptado

- **La copia puede quedar desactualizada.** Si alguien cambia la hora de
  un bloque directamente en Agenda (hoy nadie lo hace: el único que
  escribe es el propio servicio), la reserva guardada mostraría la hora
  vieja. Solo el cupo es verdad; la cita es una foto del momento de la
  reserva.
- **No hay transacción distribuida.** Primero se asegura el cupo en
  Agenda y después se inserta la reserva. Si el `INSERT` fallara después
  de asegurar el cupo, quedaría un cupo descontado sin reserva y hoy no
  hay compensación automática. Aceptamos esa ventana de inconsistencia
  porque es estrecha y se puede corregir liberando el cupo a mano.
- **Dos despliegues, dos bases y dos contratos** que hay que versionar y
  documentar juntos.

## Consecuencias

- Cualquier cambio en la disponibilidad obliga a tocar el `.proto`, y por
  lo tanto a regenerar stubs y a revisar el cliente de Reservas.
- Si el volumen de reservas creciera, la lectura de reservas ya no
  golpearía Agenda, pero la escritura sí: habría que mirar el cuello de
  botella en la llamada gRPC.
- Si Agenda necesitara exponer su información a terceros, habría que
  agregarle una fachada: hoy es un servicio interno y no tiene cara
  pública.
