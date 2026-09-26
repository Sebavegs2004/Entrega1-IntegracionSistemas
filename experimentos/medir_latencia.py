import argparse
import csv
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

BASE = os.environ.get("API_BASE", "http://localhost:5000")
API_KEY = os.environ.get("API_KEY", "clave-secreta-vet-2026")
RUTA = "/v1/bloques"
DEL_CMD = ["docker", "compose", "exec", "redis_cache",
           "redis-cli", "del", "cache:bloques"]


def borrar_cache():
    subprocess.run(DEL_CMD, cwd=PROJECT_ROOT, check=True,
                   capture_output=True)


def medir():
    req = urllib.request.Request(BASE + RUTA, headers={"X-API-Key": API_KEY})
    try:
        inicio = time.perf_counter()
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
            status = r.status
        fin = time.perf_counter()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Error: status {e.code} en GET {RUTA}")
    except urllib.error.URLError as e:
        raise SystemExit(f"No se pudo conectar con {BASE}: {e.reason}")
    if status != 200:
        raise SystemExit(f"Error: status {status} en GET {RUTA}")
    return (fin - inicio) * 1000.0


def pedir(veces):
    for _ in range(veces):
        medir()


def percentil(vals, p):
    ordenado = sorted(vals)
    if len(ordenado) == 1:
        return ordenado[0]
    k = (len(ordenado) - 1) * p / 100.0
    i = int(k)
    fracc = k - i
    if i + 1 < len(ordenado):
        return ordenado[i] + (ordenado[i + 1] - ordenado[i]) * fracc
    return ordenado[i]


def resumen(vals):
    return {
        "promedio": statistics.mean(vals),
        "p50": percentil(vals, 50),
        "p90": percentil(vals, 90),
        "p95": percentil(vals, 95),
        "min": min(vals),
        "max": max(vals),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Mide latencia de GET /v1/bloques con y sin caché.")
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()

    n = args.n
    warmup = args.warmup

    print(f"API: {BASE}{RUTA}  |  N={n} por modo  |  warmup={warmup}")

    print("Calentamiento (no medido)...")
    pedir(warmup)

    print("Bloque sin_cache (borra caché antes de cada petición)...")
    sin_cache = []
    for i in range(n):
        borrar_cache()
        sin_cache.append(medir())

    print("Warmup de caché (puebla Redis)...")
    pedir(1)

    print("Bloque cache (hits)...")
    con_cache = []
    for i in range(n):
        lat = medir()
        con_cache.append(lat)
        if lat > 200:
            print(f"Aviso: medición 'cache' nº{i + 1} alta ({lat:.1f} ms), "
                  "posible miss por TTL")

    filas = []
    for i, v in enumerate(sin_cache):
        filas.append({"tipo": "sin_cache", "iteracion": i + 1,
                      "latencia_ms": f"{v:.3f}"})
    for i, v in enumerate(con_cache):
        filas.append({"tipo": "cache", "iteracion": i + 1,
                      "latencia_ms": f"{v:.3f}"})

    lat_csv = os.path.join(SCRIPT_DIR, "latencia_bloques.csv")
    with open(lat_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tipo", "iteracion", "latencia_ms"])
        w.writeheader()
        w.writerows(filas)

    cab = ["promedio", "p50", "p90", "p95", "min", "max"]
    res_csv = os.path.join(SCRIPT_DIR, "resumen_latencia.csv")
    with open(res_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["tipo"] + cab)
        w.writeheader()
        for tipo, vals in (("sin_cache", sin_cache), ("cache", con_cache)):
            r = resumen(vals)
            w.writerow({"tipo": tipo, **{c: f"{r[c]:.3f}" for c in cab}})

    print(f"\nResultados (ms):")
    print(f"{'tipo':<12}" + "".join(f"{c:>10}" for c in cab))
    for tipo, vals in (("sin_cache", sin_cache), ("cache", con_cache)):
        r = resumen(vals)
        print(f"{tipo:<12}" + "".join(f"{r[c]:>10.3f}" for c in cab))

    print(f"\nCSV generados:")
    print(f"  {lat_csv}")
    print(f"  {res_csv}")


if __name__ == "__main__":
    main()