// =============================================================
//  CLIENTE gRPC EN .NET — Segundo cliente de Agenda
//
//  Consume el MISMO servidor (Python) a partir del MISMO .proto
//  (contracts/agenda.proto). Ninguno de los dos lados sabe en
//  qué lenguaje está el otro: lo único compartido es el contrato.
//
//  Todos los métodos de Agenda son UNARY (petición -> respuesta),
//  así que cada llamada es idéntica en forma a las del cliente Python.
//
//  Ejecutar dentro de la red de Docker (Agenda no expone puertos):
//      docker compose --profile cliente run --rm cliente-dotnet
// =============================================================

using Grpc.Core;
using Grpc.Net.Client;
using Agenda.V1;

// El servidor Python envía los bytes en UTF-8; forzamos la consola a UTF-8
// para que las tildes se impriman bien (dentro del contenedor .NET la
// consola puede usar otra codificación por defecto).
Console.OutputEncoding = System.Text.Encoding.UTF8;

var host = Environment.GetEnvironmentVariable("AGENDA_HOST") ?? "agenda";
var puerto = Environment.GetEnvironmentVariable("AGENDA_PORT") ?? "50051";

// El canal se crea UNA vez y se reutiliza, igual que en Python.
// timeout de 10s por llamada, como el cliente real de Reservas (3s).
using var canal = GrpcChannel.ForAddress($"http://{host}:{puerto}");
var cliente = new AgendaService.AgendaServiceClient(canal);
var opciones = new CallOptions(deadline: DateTime.UtcNow.AddSeconds(10));

void Titulo(string texto)
{
    Console.WriteLine();
    Console.WriteLine(new string('=', 70));
    Console.WriteLine(texto);
    Console.WriteLine(new string('=', 70));
}

// --------------------------------------------------- 1. LISTAR BLOQUES
Titulo("1 · ListarBloques (sin filtros) — todos los bloques del seed");

var respuesta = await cliente.ListarBloquesAsync(new ListarBloquesRequest(), opciones);
Console.WriteLine($"   {respuesta.Bloques.Count} bloques:");

foreach (var b in respuesta.Bloques)
{
    string estado = b.CuposLibres > 0
        ? $"{b.CuposLibres} cupo(s) libre(s)"
        : "AGOTADO";
    Console.WriteLine(
        $"   #{b.Id,-3} {b.Fecha}  {b.HoraInicio}-{b.HoraFin}  " +
        $"{b.NombreVeterinario,-22} ({b.Especialidad})  -> {estado}");
}

// ----------------------------------------------- 1b. FILTRO POR VETERINARIO
Titulo("1b · ListarBloques con filtro id_veterinario = 1");

var filtrados = await cliente.ListarBloquesAsync(
    new ListarBloquesRequest { IdVeterinario = 1 }, opciones);
Console.WriteLine($"   {filtrados.Bloques.Count} bloques del veterinario 1 " +
                  "(todos deberían ser de Dra. Carmen Rojas):");
foreach (var b in filtrados.Bloques)
    Console.WriteLine($"   #{b.Id,-3} {b.Fecha}  {b.HoraInicio}  " +
                      $"{b.NombreVeterinario} — cupos {b.CuposLibres}");

// ------------------------------------------------ 2. CONSULTAR VETERINARIO
Titulo("2 · ConsultarVeterinario(1, 1) — datos del veterinario + cupos");

try
{
    var vet = await cliente.ConsultarVeterinarioAsync(
        new ConsultarVeterinarioRequest { IdVeterinario = 1, IdBloque = 1 },
        opciones);
    Console.WriteLine($"   id={vet.IdVeterinario}  {vet.Nombre}  " +
                      $"[{vet.Especialidad}]");
    Console.WriteLine($"   cupos_libres={vet.CuposLibres}  disponible={vet.Disponible}");
}
catch (RpcException e)
{
    Console.WriteLine($"   ERROR gRPC: {e.StatusCode} — {e.Status.Detail}");
}

// ------------------------------------- 2b. MANEJO DE ERRORES (paridad con Python)
Titulo("2b · ConsultarVeterinario con id inexistente (id=99999)");

try
{
    await cliente.ConsultarVeterinarioAsync(
        new ConsultarVeterinarioRequest { IdVeterinario = 99999, IdBloque = 1 },
        opciones);
    Console.WriteLine("   (no debería llegar aquí)");
}
catch (RpcException e)
{
    Console.WriteLine($"   código:  {e.StatusCode}");
    Console.WriteLine($"   detalle: {e.Status.Detail}");
    Console.WriteLine();
    Console.WriteLine("   -> Es el MISMO código de estado (NOT_FOUND) que " +
                      "lanza el servidor Python por gRPC.");
}

// ----------------------------------- 3. CICLO COMPLETO: RESERVAR + LIBERAR
Titulo("3 · ReservarCupo + LiberarCupo — escritura interoperable");

var bloqueElegido = respuesta.Bloques.FirstOrDefault(b => b.CuposLibres > 0);
if (bloqueElegido is null)
{
    Console.WriteLine("   No hay bloques con cupos libres para demostrar la escritura.");
}
else
{
    Console.WriteLine($"   Bloque elegido: #{bloqueElegido.Id} " +
                      $"{bloqueElegido.Fecha} {bloqueElegido.HoraInicio}");
    Console.WriteLine($"   cupos antes de reservar: {bloqueElegido.CuposLibres}");

    var reserva = await cliente.ReservarCupoAsync(
        new ReservarCupoRequest { IdBloque = bloqueElegido.Id }, opciones);
    Console.WriteLine($"   -> ReservarCupo: exito={reserva.Exito}  " +
                      $"mensaje=\"{reserva.Mensaje}\"");
    if (reserva.Exito && reserva.Bloque is not null)
        Console.WriteLine($"      cupos después de reservar: {reserva.Bloque.CuposLibres} " +
                          $"(bajó 1 en la base del servidor Python)");

    var libera = await cliente.LiberarCupoAsync(
        new LiberarCupoRequest { IdBloque = bloqueElegido.Id }, opciones);
    Console.WriteLine($"   -> LiberarCupo: exito={libera.Exito}  " +
                      $"mensaje=\"{libera.Mensaje}\" — cupo restaurado, " +
                      "la base queda como estaba.");
}

// ------------------------------------------------------------- CIERRE
Console.WriteLine();
Console.WriteLine(new string('=', 70));
Console.WriteLine("Fin. Este cliente C# habló con el MISMO servidor Python,");
Console.WriteLine("usando el MISMO contrato (contracts/agenda.proto).");
Console.WriteLine(new string('=', 70));