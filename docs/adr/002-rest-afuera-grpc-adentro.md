# ADR-002 · REST hacia afuera, gRPC hacia adentro

Estado: aceptada
Responde a: D2 (por qué cada protocolo donde está) · T2 (API REST versionada) · T4 (servicio interno en gRPC)

## Contexto

La API de Reservas es el punto de entrada del sistema: la consume el
personal de la clínica desde el navegador y, más adelante, un portal web.
La consulta de disponibilidad a Agenda es interna, de alto volumen y no
la ve el exterior.

Ese reparto de tráfico es lo que decide el protocolo de cada tramo: el
tramo público tiene que ser consumible por cualquier cliente HTTP, y el
tramo interno tiene que ser barato y tipado.

## Alternativas consideradas

- **Opción A — gRPC en ambos lados.** Ofrece el mismo contrato binario y
  tipado en toda la cadena, sin traducir nada. Cuesta que un navegador
  no puede llamar gRPC: la interfaz web de Bootstrap y cualquier
  formulario de la recepción necesitarían un proxy o un gateway, y el
  contrato público dejaría de ser autodocumentado para el usuario final.
- **Opción B — REST en ambos lados.** Ofrece que todo se prueba con
  `curl`, se cachea con cachés HTTP y se documenta con OpenAPI de
  extremo a extremo. Cuesta más bytes por mensaje y tipado por
  convención (nada obliga a que el cliente y el servidor coincidan en los
  campos), justo en el tramo más caliente del sistema.
- **Opción C — REST hacia afuera y gRPC hacia adentro, modo Unary.**
  Es la elegida.

## Decisión

La API pública de Reservas es REST y se documenta en `openapi.yaml`; la
comunicación con Agenda es gRPC sobre el `.proto`, y las tres
operaciones son **Unary**.

## Justificación

**Por qué REST afuera.** Es lo que puede consumir un navegador sin
helpers: la interfaz web habla REST con `/v1/reservas` y funciona. Es
inspeccionable con `curl` o con las herramientas del navegador, lo que
baja el costo de depurar. Sus códigos de estado (200, 201, 204, 400,
404, 409, 503) son parte del contrato y se documentan en OpenAPI. Y es
cacheable: es exactamente lo que nos permitió meter Redis en
`/v1/bloques`, la consulta que más se repite.

**Por qué gRPC adentro.** Es tráfico interno, entre dos servicios que se
despliegan juntos, donde lo que importa es el costo por mensaje y que el
contrato no se rompa en silencio. El `.proto` genera el cliente y los
stubs: si alguien agrega un campo, el compilador obliga a los dos lados.
El modo **Unary** encaja porque las tres operaciones son consultas o
actualizaciones puntuales (`ListarBloques`, `ReservarCupo`,
`LiberarCupo`): cada una es un mensaje de ida y uno de vuelta. El
streaming solo sería justificable si el servidor empujara datos al
cliente sin que pregunte, y aquí siempre es el cliente quien pregunta.

**Sobre los números.** El trabajo cuantitativo (tamaño de un mismo
recurso en protobuf frente a JSON y latencia de la consulta de
disponibilidad con y sin caché) sale del experimento del informe, no de
este ADR. Acá va la dirección de la decisión; las cifras y sus matices
van en el experimento. Afirmar porcentajes sin medirlos sería
exactamente el tipo de afirmación que un ADR debe evitar.

## Costo aceptado

- **Dos contratos que se pueden desincronizar**: `openapi.yaml` y
  `agenda.proto` documentan cosas distintas y hay que actualizar los dos
  cuando cambia el dominio. Un cliente generado desde el `.proto` no
  valida el `openapi.yaml` ni al revés.
- **Los errores de gRPC no se traducen solos**: cada `RpcError` hay que
  mapearlo a un código HTTP a mano (ver ADR-004). Es código repetido que
  puede olvidarse.
- **Aprender protobuf y su cadena de herramientas** (stubs,
  `grpcurl`) es un costo de entrada para el equipo.
- **Interoperabilidad por la vía fácil**: si otro lenguaje quiere
  consumir Agenda, necesita sus propios stubs, no basta con abrir una URL.

## Consecuencias

- La interfaz web y la colección de Postman solo necesitan hablar HTTP.
- Cada vez que se toca el `.proto` hay que regenerar los stubs y volver a
  construir la imagen.
- Si algún día un tercero necesitara los datos de Agenda, la respuesta
  natural es la Opción A (gRPC en ambos lados) más un gateway, o una
  fachada REST como la que ya es Reservas.
- El `.proto` queda como fuente única de verdad de la parte interna y
  `openapi.yaml` como fuente única de verdad de la parte pública; ambos
  están versionados en el repositorio.
