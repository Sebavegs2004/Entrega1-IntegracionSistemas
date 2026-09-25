# ============================================================
# Cliente gRPC .NET — build en la imagen SDK, run en la imagen
# runtime. Así no hace falta tener .NET instalado en el host.
#
# Grpc.Tools compila contracts/agenda.proto a C# dentro del build.
# ============================================================
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src

# Copiamos el contrato (fuente única de verdad) y el proyecto.
COPY contracts/ contracts/
COPY cliente-dotnet/ cliente-dotnet/

WORKDIR /src/cliente-dotnet
RUN dotnet publish -c Release -o /out

# Imagen final: solo el runtime (sin el SDK, mucho más liviana).
FROM mcr.microsoft.com/dotnet/runtime:8.0
WORKDIR /app
COPY --from=build /out/ .
ENTRYPOINT ["dotnet", "ClienteAgenda.dll"]