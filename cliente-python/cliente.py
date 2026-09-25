# =============================================================
#  CLIENTE gRPC EN PYTHON — Primer cliente de Agenda
#
#  Consume el MISMO servidor (Python) a partir del MISMO .proto
#  (contracts/agenda.proto). Es la contracara del cliente-dotnet:
#  mismo contrato, dos lenguajes, salida equivalente.
#
#  Todos los métodos de Agenda son UNARY (petición -> respuesta),
#  así que cada llamada es idéntica en forma a la del cliente .NET.
#
#  Ejecutar dentro de la red de Docker (Agenda no expone puertos):
#      docker compose --profile cliente run --rm cliente-python
# =============================================================
import os
import sys

import grpc

# Módulos generados por protoc en el build de la imagen
# (ver cliente-python/Dockerfile, igual que en agenda/).
import agenda_pb2 as pb
import agenda_pb2_grpc as pbg

# UTF-8 para que las tildes se impriman bien (mismo motivo que en .NET).
sys.stdout.reconfigure(encoding="utf-8")

HOST = os.environ.get("AGENDA_HOST", "agenda")
PUERTO = os.environ.get("AGENDA_PORT", "50051")
DESTINO = f"{HOST}:{PUERTO}"


def titulo(texto):
    print("\n" + "=" * 70)
    print(texto)
    print("=" * 70)


def main():
    # El canal se crea UNA vez y se reutiliza, igual que en .NET.
    # timeout de 10s por llamada, como el cliente real de Reservas (3s).
    with grpc.insecure_channel(DESTINO) as canal:
        stub = pbg.AgendaServiceStub(canal)

        # ----------------------------------------- 1. LISTAR BLOQUES
        titulo("1 · ListarBloques (sin filtros) — todos los bloques del seed")

        respuesta = stub.ListarBloques(pb.ListarBloquesRequest(),
                                       timeout=10)
        print(f"   {len(respuesta.bloques)} bloques:")

        for b in respuesta.bloques:
            estado = f"{b.cupos_libres} cupo(s) libre(s)" if b.cupos_libres > 0 \
                else "AGOTADO"
            print(f"   #{b.id:<3} {b.fecha}  {b.hora_inicio}-{b.hora_fin}  "
                  f"{b.nombre_veterinario:<22} ({b.especialidad})  -> {estado}")

        # ----------------------------- 1b. FILTRO POR VETERINARIO
        titulo("1b · ListarBloques con filtro id_veterinario = 1")

        filtrados = stub.ListarBloques(
            pb.ListarBloquesRequest(id_veterinario=1), timeout=10)
        print(f"   {len(filtrados.bloques)} bloques del veterinario 1 "
              "(todos deberían ser de Dra. Carmen Rojas):")
        for b in filtrados.bloques:
            print(f"   #{b.id:<3} {b.fecha}  {b.hora_inicio}  "
                  f"{b.nombre_veterinario} — cupos {b.cupos_libres}")

        # -------------------------------- 2. CONSULTAR VETERINARIO
        titulo("2 · ConsultarVeterinario(1, 1) — datos del veterinario + cupos")

        try:
            vet = stub.ConsultarVeterinario(
                pb.ConsultarVeterinarioRequest(id_veterinario=1,
                                               id_bloque=1),
                timeout=10)
            print(f"   id={vet.id_veterinario}  {vet.nombre}  "
                  f"[{vet.especialidad}]")
            print(f"   cupos_libres={vet.cupos_libres}  "
                  f"disponible={vet.disponible}")
        except grpc.RpcError as e:
            print(f"   ERROR gRPC: {e.code().name} — {e.details()}")

        # --------------------------- 2b. MANEJO DE ERRORES (paridad con .NET)
        titulo("2b · ConsultarVeterinario con id inexistente (id=99999)")

        try:
            stub.ConsultarVeterinario(
                pb.ConsultarVeterinarioRequest(id_veterinario=99999,
                                               id_bloque=1),
                timeout=10)
            print("   (no debería llegar aquí)")
        except grpc.RpcError as e:
            print(f"   código:  {e.code().name}")
            print(f"   detalle: {e.details()}")
            print()
            print("   -> Es el código de estado NOT_FOUND que el servidor")
            print("      devuelve por gRPC, igual que lo ve el cliente .NET.")

        # ----------------------- 3. CICLO COMPLETO: RESERVAR + LIBERAR
        titulo("3 · ReservarCupo + LiberarCupo — escritura interoperable")

        bloque_elegido = next((b for b in respuesta.bloques
                               if b.cupos_libres > 0), None)
        if bloque_elegido is None:
            print("   No hay bloques con cupos libres para demostrar la escritura.")
        else:
            print(f"   Bloque elegido: #{bloque_elegido.id} "
                  f"{bloque_elegido.fecha} {bloque_elegido.hora_inicio}")
            print(f"   cupos antes de reservar: {bloque_elegido.cupos_libres}")

            reserva = stub.ReservarCupo(
                pb.ReservarCupoRequest(id_bloque=bloque_elegido.id),
                timeout=10)
            print(f"   -> ReservarCupo: exito={reserva.exito}  "
                  f"mensaje=\"{reserva.mensaje}\"")
            if reserva.exito and reserva.bloque:
                print(f"      cupos después de reservar: "
                      f"{reserva.bloque.cupos_libres} "
                      f"(bajó 1 en la base del servidor Python)")

            libera = stub.LiberarCupo(
                pb.LiberarCupoRequest(id_bloque=bloque_elegido.id),
                timeout=10)
            print(f"   -> LiberarCupo: exito={libera.exito}  "
                  f"mensaje=\"{libera.mensaje}\" — cupo restaurado, "
                  "la base queda como estaba.")

        # --------------------------------------------------- CIERRE
        print()
        print("=" * 70)
        print("Fin. Este cliente Python habló con el MISMO servidor,")
        print("usando el MISMO contrato (contracts/agenda.proto).")
        print("Compare este output con el de cliente-dotnet/Program.cs:")
        print("mismo contrato compartido, dos implementaciones.")
        print("=" * 70)


if __name__ == "__main__":
    main()