# Imagen del primer cliente de Agenda (Python)
# Misma estrategia que el servicio: se generan los stubs desde el
# .proto en el build y el cliente solo importa los módulos.
FROM python:3.12-slim

WORKDIR /app

COPY contracts/agenda.proto contracts/agenda.proto
COPY cliente-python/cliente.py cliente.py

RUN pip install --no-cache-dir grpcio grpcio-tools

# Aunque el .proto declare package agenda.v1, el plugin de Python
# genera los módulos planos en /app (agenda_pb2.py y agenda_pb2_grpc.py).
RUN python -m grpc_tools.protoc -I contracts --python_out=. --grpc_python_out=. contracts/agenda.proto

CMD ["python", "cliente.py"]