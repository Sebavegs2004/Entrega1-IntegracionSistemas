FROM python:3.12-slim

WORKDIR /app

COPY agenda/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Compilar el contrato .proto dentro de la imagen (fuente única de verdad: contracts/)
COPY contracts/agenda.proto /app/contracts/agenda.proto
RUN mkdir -p /app/src && python -m grpc_tools.protoc -I /app/contracts \
    --python_out=/app/src --grpc_python_out=/app/src \
    /app/contracts/agenda.proto

COPY agenda/src /app/src

ENV AGENDA_DB_PATH=/data/agenda.db
VOLUME ["/data"]
EXPOSE 50051

CMD ["python", "src/server.py"]
