#!/usr/bin/env bash
# ============================================================
# Regenera los stubs de gRPC (agenda_pb2.py y agenda_pb2_grpc.py)
# a partir de contracts/agenda.proto.
#
# Nota: Docker ya los genera al construir las imágenes; este script
# sirve si quieres ejecutar los servicios en tu máquina (sin Docker).
# Requisito: pip install grpcio-tools
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

python -m grpc_tools.protoc -I contracts \
  --python_out=agenda --grpc_python_out=agenda \
  contracts/agenda.proto

python -m grpc_tools.protoc -I contracts \
  --python_out=reservas --grpc_python_out=reservas \
  contracts/agenda.proto

echo "Stubs generados en agenda/ y reservas/"