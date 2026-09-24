# Imagen del servicio de pruebas de contrato.
# Corre la suite completa dentro de la red de Docker:
#   - test_openapi.py : contrato REST contra http://reservas:5000
#   - test_proto.py   : contrato gRPC contra agenda:50051
FROM python:3.12-slim

WORKDIR /app

# Contratos (para leer openapi.yaml y compilar agenda.proto en los tests).
COPY contracts/ contracts/
COPY tests/ tests/

# Dependencias de los tests (pytest + validación de specs + gRPC).
RUN pip install --no-cache-dir -r /app/tests/requirements.txt

# Generamos stubs frescos a partir del contrato dentro de la imagen,
# así los tests usan siempre el .proto actual (test_proto también
# regenera los suyos en un tmpdir, esto es solo como red de seguridad).
RUN python -m grpc_tools.protoc \
    -I /app/contracts \
    --python_out=/app/tests --grpc_python_out=/app/tests \
    /app/contracts/agenda.proto

CMD ["pytest", "-v", "/app/tests"]