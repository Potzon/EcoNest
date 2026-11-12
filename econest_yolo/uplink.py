"""Puente MQTT -> backend REST.

Escucha `mqtt.output_topic` (lo que publica econest_yolo.service), traduce cada
mensaje al contrato del backend y lo envía con POST /detections usando el token
del dispositivo. Se ejecuta como proceso aparte:

    python -m econest_yolo.uplink --config config.yaml

Así la cámara y YOLO siguen funcionando aunque no haya red: el broker local
desacopla ambos lados y este puente reintenta cuando vuelve la conexión.
"""
import argparse
import json
import logging
import queue
import threading
import time

import httpx
import paho.mqtt.client as mqtt

from .config import BackendConfig, Config, load_config

log = logging.getLogger("econest_yolo.uplink")


def to_backend_payload(msg: dict, device_id: str, max_screenshot_bytes: int = 2_000_000) -> dict:
    """Traduce el JSON de econest_yolo al de POST /detections.

    - bbox: [x1, y1, x2, y2] -> [x, y, w, h]
    - image_b64 -> screenshot (se omite si supera el límite del backend)
    - NO se envían `count` ni `location`: el backend los deriva de las
      detecciones y del dispositivo registrado.
    """
    detections = []
    for d in msg["detections"]:
        x1, y1, x2, y2 = d["bbox_xyxy"]
        detections.append(
            {"class": d["class"], "confidence": d["confidence"], "bbox": [x1, y1, x2 - x1, y2 - y1]}
        )
    out = {"device_id": device_id, "timestamp": msg["timestamp"], "detections": detections}
    b64 = msg.get("image_b64")
    if b64:
        if len(b64) * 3 // 4 <= max_screenshot_bytes:
            out["screenshot"] = b64
        else:
            log.warning("captura demasiado grande para el backend; se envía sin imagen")
    return out


class Uplink:
    """Cola acotada + hilo que envía con reintentos y espera exponencial."""

    def __init__(self, cfg: BackendConfig, http: httpx.Client | None = None):
        self.cfg = cfg
        self.http = http or httpx.Client(
            base_url=cfg.url,
            timeout=cfg.timeout,
            headers={"Authorization": f"Bearer {cfg.token}"},
        )
        self.queue: queue.Queue[dict] = queue.Queue(maxsize=cfg.queue_size)

    def submit(self, msg: dict) -> None:
        try:
            self.queue.put_nowait(msg)
        except queue.Full:
            log.error("cola llena (%d): detección descartada", self.cfg.queue_size)

    def send(self, msg: dict) -> bool:
        """True = terminado (enviado o inviable); False = reintentar más tarde."""
        try:
            payload = to_backend_payload(msg, self.cfg.device_id, self.cfg.max_screenshot_bytes)
            r = self.http.post("/detections", json=payload)
        except (KeyError, ValueError, TypeError) as e:
            log.error("mensaje con formato inesperado, descartado: %r", e)
            return True
        except httpx.TransportError as e:
            log.warning("backend inaccesible: %s", e)
            return False
        if r.status_code == 201:
            log.info("detección enviada (id=%s)", r.json().get("id"))
            return True
        if r.status_code >= 500 or r.status_code in (408, 429):
            log.warning("backend respondió %s; se reintentará", r.status_code)
            return False
        # 4xx: reintentar no lo arreglará (token mal, payload inválido...).
        log.error("backend rechazó la detección (%s): %s", r.status_code, r.text[:200])
        return True

    def worker(self) -> None:
        while True:
            msg = self.queue.get()
            delay = 1.0
            while not self.send(msg):
                time.sleep(delay)
                delay = min(delay * 2, 60.0)
            self.queue.task_done()


def run(cfg: Config) -> None:
    b = cfg.backend
    if not (b.url and b.device_id and b.token):
        raise SystemExit("Faltan backend.url, backend.device_id o ECONEST_DEVICE_TOKEN")
    uplink = Uplink(b)
    threading.Thread(target=uplink.worker, daemon=True).start()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt.username:
        client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)

    def on_connect(c, userdata, flags, reason_code, properties):
        log.info("conectado a MQTT (%s), suscrito a %s", reason_code, cfg.mqtt.output_topic)
        c.subscribe(cfg.mqtt.output_topic, qos=1)

    def on_message(c, userdata, m):
        try:
            uplink.submit(json.loads(m.payload))
        except json.JSONDecodeError as e:
            log.warning("mensaje MQTT no es JSON: %s", e)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg.mqtt.host, cfg.mqtt.port)
    client.loop_forever()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="EcoNest: puente MQTT -> backend REST")
    p.add_argument("--config", help="ruta a config.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(load_config(args.config))
