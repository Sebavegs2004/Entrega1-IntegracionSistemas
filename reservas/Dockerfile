# Imagen del servicio Reservas (Flask API REST + interfaz web)
FROM python:3.12-slim

WORKDIR /app

# Copiamos los contratos (agenda.proto para generarlos + openapi.yaml
# para Swagger) y los scripts .sql que crean las tablas en SQLite.
COPY contracts/ contracts/
COPY sql/ sql/
COPY reservas/ .

# Instalamos dependencias (Flask + gRPC + Redis).
RUN pip install --no-cache-dir -r requirements.txt

# Generamos los stubs de Python del cliente gRPC (agenda_pb2*.py en /app).
RUN python -m grpc_tools.protoc -I contracts --python_out=. --grpc_python_out=. contracts/agenda.proto

# Carpeta del archivo SQLite (docker-compose la monta como volumen).
RUN mkdir -p /data

# Puerta de entrada de la API y la interfaz web.
EXPOSE 5000

CMD ["python", "app.py"]
