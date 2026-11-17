"""Heartbeat de la Raspberry -> POST /devices/me/status.

Envía cada `heartbeat_interval` segundos las métricas del sistema (temperatura
de CPU, carga, memoria, disco, uptime). Todas son opcionales en el backend: si
una no se puede leer (p. ej. `/proc` no disponible), se envía sin ella; si no
se puede leer ninguna, se envía un heartbeat vacío, que igualmente indica que
el dispositivo está vivo. La hora la pone el servidor.

Puede correr de dos formas:

- Integrado: `uplink.run()` arranca este bucle en un hilo en segundo plano.
- Solo: `python -m econest_yolo.heartbeat --config config.yaml`
"""
import argparse
import logging
import os
import shutil
import threading
import time
from pathlib import Path

import httpx

from .config import BackendConfig, load_config

log = logging.getLogger("econest_yolo.heartbeat")

# Rangos del contrato del backend (schemas.py, DeviceStatusIn). Se recortan aquí
# para que una lectura absurda del sistema nunca dé un 422 en cada latido.
_LIMITS = {
    "cpu_temp_c": (-50.0, 150.0),
    "load_1m": (0.0, 1000.0),
    "mem_used_pct": (0.0, 100.0),
    "disk_used_pct": (0.0, 100.0),
    "uptime_s": (0, None),
}


def _clamp(key: str, value: float):
    low, high = _LIMITS[key]
    if value < low:
        return low
    if high is not None and value > high:
        return high
    # uptime_s es entero; el resto, float redondeado (Grafana no necesita más)
    return int(value) if key == "uptime_s" else round(value, 1)


def collect_metrics() -> dict:
    """Lee lo que pueda del sistema; devuelve solo las métricas disponibles."""
    out: dict = {}

    try:  # temperatura de la CPU (miliºC); funciona en Raspberry Pi OS
        raw = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip())
        out["cpu_temp_c"] = _clamp("cpu_temp_c", raw / 1000.0)
    except (OSError, ValueError):
        pass

    try:  # carga media del último minuto
        out["load_1m"] = _clamp("load_1m", os.getloadavg()[0])
    except (OSError, AttributeError):
        pass

    try:  # % de RAM usada: (total - disponible) / total
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.strip().split()[0])  # kB
        total, avail = info["MemTotal"], info["MemAvailable"]
        out["mem_used_pct"] = _clamp("mem_used_pct", (total - avail) / total * 100)
    except (OSError, ValueError, KeyError):
        pass

    try:  # % de disco usado en la raíz
        usage = shutil.disk_usage("/")
        out["disk_used_pct"] = _clamp("disk_used_pct", usage.used / usage.total * 100)
    except OSError:
        pass

    try:  # segundos desde el arranque
        out["uptime_s"] = _clamp("uptime_s", float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError):
        pass

    return out


class Heartbeat:
    """Bucle que hace POST /devices/me/status cada `interval` segundos.

    No es crítico: si el backend no responde, se registra y se espera al
    siguiente latido (sin cola ni reintentos, a diferencia del uplink).
    """

    def __init__(self, cfg: BackendConfig, http: httpx.Client | None = None, interval: float | None = None):
        self.interval = interval if interval is not None else cfg.heartbeat_interval
        self.http = http or httpx.Client(base_url=cfg.url, timeout=cfg.timeout)
        # Cabecera por petición: no depende de cómo se haya creado el cliente.
        self._headers = {"Authorization": f"Bearer {cfg.token}"} if cfg.token else {}
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def beat(self) -> bool:
        """Un latido. True = aceptado por el backend."""
        try:
            r = self.http.post("/devices/me/status", json=collect_metrics(), headers=self._headers)
        except httpx.TransportError as e:
            log.warning("backend inaccesible para el heartbeat: %s", e)
            return False
        if r.status_code == 201:
            return True
        log.error("el backend rechazó el heartbeat (%s): %s", r.status_code, r.text[:200])
        return False

    def run_loop(self) -> None:
        # Primer latido inmediato: el dispositivo aparece "online" en cuanto arranca.
        while not self._stop.is_set():
            self.beat()
            self._stop.wait(self.interval)


def start_background(cfg: BackendConfig, http: httpx.Client | None = None) -> Heartbeat:
    """Arranca el heartbeat en un hilo daemon (lo usa el uplink)."""
    hb = Heartbeat(cfg, http)
    threading.Thread(target=hb.run_loop, daemon=True, name="heartbeat").start()
    return hb


def run(cfg) -> None:
    b = cfg.backend
    if not (b.url and b.device_id and b.token):
        raise SystemExit("Faltan backend.url, backend.device_id o ECONEST_DEVICE_TOKEN")
    log.info("heartbeat cada %.0f s hacia %s (device %s)", b.heartbeat_interval, b.url, b.device_id)
    Heartbeat(b).run_loop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="EcoNest: heartbeat de la Raspberry al backend")
    p.add_argument("--config", help="ruta a config.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(load_config(args.config))
