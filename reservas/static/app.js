/* ============================================================
   Interfaz web VidaAnimal — JavaScript puro (Vanilla JS)
   Consume la API REST de Reservas (/v1) con fetch.
   ============================================================ */

// Misma clave que define el servidor (API_KEY en app.py).
const API_KEY = "clave-secreta-vet-2026";
const $ = (sel) => document.querySelector(sel);

// Estado de la aplicación (todo se vuelve a cargar desde la API)
let bloques = [];
let duenos = [];
let reservas = [];
let bloqueSeleccionado = null; // bloque elegido para reservar en el formulario
let diaActivo = null;          // fecha "AAAA-MM-DD" o null = ver todos

/* ------------------------------------------------------------
   Ayudante para llamar a la API
   ------------------------------------------------------------ */
async function api(path, opciones = {}) {
  const config = {
    method: "GET",
    headers: { "X-API-Key": API_KEY, "Content-Type": "application/json" },
    ...opciones,
  };
  const res = await fetch(`/v1${path}`, config);
  if (!res.ok) {
    // Si el servidor responde JSON con "mensaje", lo mostramos tal cual.
    let msg = `Error ${res.status}`;
    try {
      const datos = await res.json();
      if (datos.mensaje) msg = datos.mensaje;
    } catch (_) { /* sin JSON: dejamos el mensaje genérico */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;   // DELETE sin contenido
  return res.json();
}

/* Formatea "2026-09-23" -> "mié 23 sep." */
function fmtFecha(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("es-CL",
    { weekday: "short", day: "numeric", month: "short" });
}

function aviso(mensaje, tipo = "success") {
  const cont = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${tipo} border-0`;
  el.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">${mensaje}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto"
              data-bs-dismiss="toast" aria-label="Cerrar"></button>
    </div>`;
  cont.appendChild(el);
  const toast = new bootstrap.Toast(el, { delay: 3500 });
  el.addEventListener("hidden.bs.toast", () => el.remove());
  toast.show();
}

/* ------------------------------------------------------------
   Carga inicial: bloques, dueños y reservas en paralelo
   ------------------------------------------------------------ */
async function cargarTodo() {
  await Promise.all([
    cargarBloques().catch((e) => aviso(e.message, "danger")),
    cargarDuenos().catch((e) => aviso(e.message, "danger")),
    cargarReservas().catch((e) => aviso(e.message, "danger")),
  ]);
}

/* ------------------------------------------------------------
   1) Bloques disponibles (vienen de Agenda vía /v1/bloques)
   ------------------------------------------------------------ */
async function cargarBloques() {
  bloques = await api("/bloques");
  diaActivo = null;        // al recargar, volvemos a "ver todos"
  pintarDias();
  pintarTablaBloques();
}

function pintarDias() {
  // Sumamos cupos libres por fecha y tomamos las 5 fechas más próximas.
  const porFecha = {};
  bloques.forEach((b) => { porFecha[b.fecha] = (porFecha[b.fecha] || 0) + b.cupos_libres; });

  const cont = $("#dias");
  cont.innerHTML = "";
  const fechas = Object.keys(porFecha).sort();

  if (!fechas.length) {
    cont.innerHTML = '<span class="va-dias-nota">Sin cupos próximos.</span>';
    return;
  }

  fechas.slice(0, 5).forEach((fecha) => {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = "va-dia" + (diaActivo === fecha ? " activo" : "");
    const [y, m, d] = fecha.split("-").map(Number);
    const nombre = new Date(y, m - 1, d).toLocaleDateString("es-CL", { weekday: "short" });
    boton.innerHTML = `<span>${nombre}</span><span class="va-dia-cupos">${porFecha[fecha]}</span>`;
    boton.addEventListener("click", () => {
      // Clic de nuevo en el día activo = quitar el filtro.
      diaActivo = diaActivo === fecha ? null : fecha;
      pintarDias();
      pintarTablaBloques();
    });
    cont.appendChild(boton);
  });
}

function pintarTablaBloques() {
  const tbody = $("#cuerpoBloques");
  const filtrados = bloques.filter((b) => !diaActivo || b.fecha === diaActivo);

  if (!filtrados.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="text-center va-vacio">' +
      'No hay bloques para mostrar.</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  filtrados.forEach((b) => {
    const tr = document.createElement("tr");
    const cupos = b.cupos_libres;
    const hayCupo = cupos > 0;

    tr.innerHTML = `
      <td>${fmtFecha(b.fecha)}</td>
      <td>${b.hora_inicio} – ${b.hora_fin}</td>
      <td>${b.nombre_veterinario}<span class="va-spec">${b.especialidad}</span></td>
      <td><span class="va-cupos">${cupos} libre${cupos === 1 ? "" : "s"}</span></td>
      <td class="text-end">${hayCupo
        ? '<button class="btn btn-va-pino btn-sm">Reservar</button>'
        : '<span class="va-agotado">Agotado</span>'}</td>`;

    const boton = tr.querySelector("button");
    if (boton) boton.addEventListener("click", () => elegirBloque(b));
    tbody.appendChild(tr);
  });
}

/* Elegir un bloque: lo mostramos en el formulario y habilitamos el botón */
function elegirBloque(b) {
  bloqueSeleccionado = b;
  const el = $("#bloqueElegido");
  el.classList.add("fijo");
  el.textContent = `${fmtFecha(b.fecha)} · ${b.hora_inicio}–${b.hora_fin} · ${b.nombre_veterinario}`;
  $("#btnReservar").disabled = false;
}

/* ------------------------------------------------------------
   2) Dueños
   ------------------------------------------------------------ */
async function cargarDuenos() {
  duenos = await api("/duenos");
  const select = $("#duenoSelect");
  const ValorActual = select.value;

  select.innerHTML = duenos.length
    ? duenos.map((d) => `<option value="${d.id_dueno}">${d.nombre} · ${d.telefono}</option>`).join("")
    : '<option value="">Primero registra un dueño (+)</option>';

  if ([...select.options].some((o) => o.value === ValorActual)) select.value = ValorActual;
}

$("#btnGuardarDueno").addEventListener("click", async () => {
  const nombre = $("#duenoNombre").value.trim();
  const telefono = $("#duenoTelefono").value.trim();
  const email = $("#duenoEmail").value.trim();

  if (!nombre || !telefono) return aviso("Nombre y teléfono son obligatorios.", "warning");

  try {
    await api("/duenos", {
      method: "POST",
      body: JSON.stringify({ nombre, telefono, email: email || undefined }),
    });
    const modal = bootstrap.Modal.getInstance($("#modalDueno"));
    modal.hide();
    $("#duenoNombre").value = "";
    $("#duenoTelefono").value = "";
    $("#duenoEmail").value = "";
    await cargarDuenos();
    aviso("Dueño registrado.");
  } catch (e) {
    aviso(e.message, "danger");
  }
});

/* ------------------------------------------------------------
   3) Crear reserva (Flask consulta el cupo a Agenda por gRPC)
   ------------------------------------------------------------ */
$("#btnReservar").addEventListener("click", async () => {
  const idDueno = $("#duenoSelect").value;
  const mascota = $("#mascotaInput").value.trim();
  const motivo = $("#motivoInput").value.trim();

  if (!idDueno) return aviso("Primero elige o registra un dueño.", "warning");
  if (!mascota) return aviso("Escribe el nombre de la mascota.", "warning");
  if (!bloqueSeleccionado) return aviso("Elige un bloque en la tabla.", "warning");

  const boton = $("#btnReservar");
  boton.disabled = true;
  try {
    await api("/reservas", {
      method: "POST",
      body: JSON.stringify({
        id_dueno: Number(idDueno),
        id_bloque: bloqueSeleccionado.id,
        mascota_nombre: mascota,
        motivo: motivo || undefined,
      }),
    });
    aviso("Reserva confirmada. El cupo quedó reservado en Agenda.", "success");

    // Limpiamos el formulario y recargamos datos para ver el nuevo estado.
    bloqueSeleccionado = null;
    $("#bloqueElegido").classList.remove("fijo");
    $("#bloqueElegido").textContent = "Elige un bloque en la tabla de la izquierda.";
    $("#mascotaInput").value = "";
    $("#motivoInput").value = "";
    await Promise.all([cargarBloques(), cargarReservas()]);
  } catch (e) {
    aviso(e.message, "danger");
  }
  boton.disabled = !bloqueSeleccionado;
});

/* ------------------------------------------------------------
   4) Reservas registradas + cancelar
   ------------------------------------------------------------ */
async function cargarReservas() {
  reservas = await api("/reservas");
  const tbody = $("#cuerpoReservas");

  if (!reservas.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center va-vacio">' +
      'Aún no hay reservas. Elige un bloque y reserva.</td></tr>';
    return;
  }

  tbody.innerHTML = "";
  reservas.forEach((r) => {
    const esActiva = r.estado === "activa";
    const dueño = duenos.find((d) => d.id_dueno === r.id_dueno);
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.mascota_nombre}</td>
      <td>${dueño ? dueño.nombre : r.id_dueno}</td>
      <td>${r.nombre_veterinario}</td>
      <td>${fmtFecha(r.fecha)} · ${r.hora_inicio}</td>
      <td><span class="va-estado va-estado-${r.estado}">${r.estado}</span></td>
      <td class="text-end">${esActiva
        ? '<button class="btn btn-va-linea btn-sm">Cancelar</button>'
        : ""}</td>`;
    const boton = tr.querySelector("button");
    if (boton) boton.addEventListener("click", () => cancelarReserva(r.id_reserva));
    tbody.appendChild(tr);
  });
}

async function cancelarReserva(idReserva) {
  try {
    await api(`/reservas/${idReserva}`, { method: "DELETE" });
    aviso("Reserva cancelada y cupo liberado en Agenda.", "success");
    await Promise.all([cargarBloques(), cargarReservas()]);
  } catch (e) {
    aviso(e.message, "danger");
  }
}

/* ------------------------------------------------------------
   Arranque
   ------------------------------------------------------------ */
cargarTodo();