# Imagen del servicio Agenda (gRPC)
FROM python:3.12-slim

WORKDIR /app

# Copiamos el contrato, los scripts .sql del esquema y el código
# del servicio
COPY contracts/agenda.proto contracts/agenda.proto
COPY sql/ sql/
COPY agenda/ .

# Instalamos dependencias. grpcio-tools se usa solo para generar stubs.
RUN pip install --no-cache-dir -r requirements.txt

# Generamos los stubs de Python a partir del .proto:
# agenda_pb2.py y agenda_pb2_grpc.py quedan en /app.
RUN python -m grpc_tools.protoc -I contracts --python_out=. --grpc_python_out=. contracts/agenda.proto

# Carpeta del archivo SQLite (docker-compose la monta como volumen).
RUN mkdir -p /data

# Puerto interno de gRPC (no se publica al host en docker-compose)
EXPOSE 50051

CMD ["python", "server.py"]
