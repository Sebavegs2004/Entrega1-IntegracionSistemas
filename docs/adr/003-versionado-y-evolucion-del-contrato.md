# ADR-003 · Versionado en la ruta y cómo evoluciona el contrato

Estado: aceptada
Responde a: D3 (contrato, versionado y evolución) · T3 (contrato explícito)

## Contexto

Hay dos contratos versionados en el repositorio: `openapi.yaml` para la
API pública y `agenda.proto` para el servicio interno. Quien los consume
no se actualiza al mismo tiempo que nosotros: la interfaz web viene con
la imagen, pero la colección de Postman, un script del personal o un
portal futuro quedan congelados en la versión que tenían el día que los
escribieron.

La consecuencia práctica es que un cambio de contrato no se puede hacer
"en el sitio": hay que poder publicar una versión nueva sin romper a
quien todavía habla la vieja.

## Alternativas consideradas

- **Opción A — Sin versionar, cambiar el contrato en el sitio.** Es lo más
  barato de mantener mientras no haya clientes externos. Cuesta que
  cualquier cambio de campo rompe en silencio a los clientes viejos: un
  cliente que mande `nombre_dueno` en vez de `nombre` empezaría a recibir
  errores sin aviso, y no hay forma de avisarles qué pasó.
- **Opción B — Versionado por header** (`Accept: application/vnd.vidaanimal.v1+json`).
  Es más limpio: la URL no cambia nunca. Cuesta que se ve en las
  herramientas, en los logs y en el navegador solo si se mira el header,
  lo que hace más lenta la depuración.
- **Opción C — Versionado en la ruta (`/v1/...`)** y `package agenda.v1`
  en el `.proto`. Es la elegida.

## Decisión

La API pública vive bajo `/v1` y la parte interna se versiona en el
`package` del `.proto` (`agenda.v1`). `/v1` y `/v2` pueden convivir: el
cambio incompatible se agrega como una versión nueva, nunca se edita la
vieja.

## Justificación

Elegimos la Opción C porque la versión queda a la vista en la URL, en los
logs del servidor y en el `curl` de quien prueba la API, sin tener que
mirar headers escondidos. Además permite una transición real: publicar
`/v2` mientras `/v1` sigue sirviendo a los clientes que no se han
actualizado, y avisar por el canal que ya usan (el repositorio y Swagger
UI en `/v1/docs`, que muestra siempre la versión vigente).

**Qué cambios son compatibles y cuáles no.** Con el contrato actual:

| Cambio | ¿Compatible? | Por qué |
|---|---|---|
| Agregar un campo **opcional** a la respuesta (ej. `email` en `Dueno`, `motivo` en `Reserva`) | Sí | Los clientes viejos ignoran lo que no conocen; los nuevos lo piden. Ya se hizo con `email` y `motivo`. |
| Agregar un campo opcional al cuerpo de una petición | Sí, con cuidado | El servidor debe seguir aceptando cuerpos que no lo manden. |
| Agregar un campo **obligatorio** | **No** | Los clientes antiguos no lo mandan y el servidor empezaría a rechazar peticiones que antes funcionaban. Obliga a `/v2`. |
| Cambiar el tipo de un campo (por ejemplo `cupos_libres` de número a texto) | **No** | Los clientes lo interpretan mal o no lo interpretan. Obliga a `/v2`. |
| Renombrar o quitar un campo | **No** | El cliente viejo sigue mandándolo o leyéndolo. |
| Agregar un código de error nuevo | Sí | Solo hay que documentarlo; un cliente que no lo conhece trata el error como "algo falló". |

Ese es el criterio que seguimos: **agregar es compatible, quitar o
endurecer no**. Por eso los campos opcionales de la respuesta se
declaran con `nullable: true` y no como obligatorios.

**Sobre `additionalProperties: false`.** El contrato lo declara en los
cuerpos de alta y la implementación sí lo respeta: los modelos de Pydantic
de `reservas/app.py` están configurados con `extra="forbid"`, así que un
campo desconocido se rechaza con un 400 en vez de ignorarse. Es la misma
razón por la que el contrato no debe adelantarse al código: acá la
validación vive en el modelo, que es lo que la hace cierta.

**Cómo se enteran los consumidores.** El cambio se versiona junto con el
código en el mismo commit que lo implementa: quien lea el historial ve en
qué commit apareció `/v2` y puede fechar su migración. La versión tampoco
se comunica por un canal especial (notas de release, correo), porque hoy
el sistema se despliega entero en un solo entorno.

## Costo aceptado

- **Mantener dos versiones en paralelo cuesta.** Cada endpoint duplicado
  es el doble de pruebas y el doble de superficie que documentar. Por eso
  solo se abre `/v2` cuando el cambio es realmente incompatible.
- **El número de versión se "+cose" en el código y en las URLs.** No es
  una constante configurable; cambiarla es editar código, y eso es
  deliberado para que no se tenga una ruta sirviendo dos contratos.
- **El `.proto` se versiona por `package`, no por archivo**, así que un
  cliente generado de la versión vieja puede vivir en la misma
  aplicación que el de la nueva sin colisionar.

## Consecuencias

- Antes de tocar un contrato hay que preguntarse si el cambio es
  compatible; si no lo es, el costo sube a "duplicar la ruta y migrar".
- Los errores documentados en `openapi.yaml` son parte del contrato: un
  `404` significa "el recurso no existe" para cualquier recurso, no solo
  para un dueño, y ese texto general es lo que permite reutilizar un
  único schema `Error`.
- La prueba automatizada que verifica que el contrato sigue
  describiendo la API real (la colección de Postman incluye una
  verificación de esto) es la que nos avisaría de una deriva entre el
  `.yaml` y el código.
