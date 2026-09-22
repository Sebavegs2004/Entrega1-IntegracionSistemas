FROM python:3.12-slim

WORKDIR /app

COPY reservas/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Compilar el contrato .proto dentro de la imagen (mismo contrato que usa Agenda)
RUN pip install --no-cache-dir grpcio-tools==1.84.0
COPY contracts/agenda.proto /app/contracts/agenda.proto
RUN mkdir -p /app/src && python -m grpc_tools.protoc -I /app/contracts \
    --python_out=/app/src --grpc_python_out=/app/src \
    /app/contracts/agenda.proto

COPY reservas/src /app/src

ENV RESERVAS_DB_PATH=/data/reservas.db
ENV AGENDA_HOST=agenda
ENV AGENDA_PORT=50051
ENV API_KEY=clave-secreta-vet-2026
VOLUME ["/data"]
EXPOSE 5000

WORKDIR /app/src
CMD ["python", "app.py"]
