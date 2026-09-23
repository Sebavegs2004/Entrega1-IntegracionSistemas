# Imagen del servicio Reservas (Flask API REST + interfaz web)
FROM python:3.12-slim

WORKDIR /app

# Copiamos los contratos (agenda.proto para generarlos + openapi.yaml para Swagger)
COPY contracts/ contracts/
COPY reservas/ .

# Instalamos dependencias (Flask + gRPC + MySQL).
RUN pip install --no-cache-dir -r requirements.txt

# Generamos los stubs de Python del cliente gRPC (agenda_pb2*.py en /app).
RUN python -m grpc_tools.protoc -I contracts --python_out=. --grpc_python_out=. contracts/agenda.proto

# Puerta de entrada de la API y la interfaz web.
EXPOSE 5000

CMD ["python", "app.py"]