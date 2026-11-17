"""Proceso principal de la Raspberry Pi: sensor de movimiento -> foto -> MQTT.

Cuando el PIR (Grove, puerto D24) detecta movimiento, saca una foto con la
webcam y la publica en `mqtt.input_topic`. A partir de ahí sigue el camino
que ya existe:

    PIR --> [motion] --(JPEG)--> econest/camera/image --> [econest_yolo]
        --(JSON)--> econest/detections --> [uplink] --> backend

    python -m econest_yolo.motion --config config.yaml

Si el PIR sigue activo (algo se queda delante), saca otra foto cada
`motion.cooldown` segundos.
"""
import argparse
import logging
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .camera import CaptureError, capture_jpeg
from .config import Config, MotionConfig, load_config

log = logging.getLogger("econest_yolo.motion")


def gpio_reader(cfg: MotionConfig) -> Callable[[], bool]:
    """Devuelve una función que lee el PIR (True = movimiento)."""
    from gpiozero import DigitalInputDevice  # import tardío: no hace falta en CI

    # pull_up=None: el PIR de Grove tiene salida activa, no necesita resistencia.
    dev = DigitalInputDevice(cfg.pin, pull_up=None, active_state=cfg.active_high)
    return lambda: bool(dev.value)


class MotionTrigger:
    """Decide cuándo sacar foto: en cuanto hay movimiento y, mientras siga
    habiéndolo, como mucho una vez cada `cooldown` segundos."""

    def __init__(self, cooldown: float):
        self.cooldown = cooldown
        self.last_shot: float | None = None

    def update(self, active: bool, now: float) -> bool:
        if not active:
            return False
        if self.last_shot is not None and now - self.last_shot < self.cooldown:
            return False
        self.last_shot = now
        return True


def loop(
    cfg: Config,
    read_motion: Callable[[], bool],
    capture: Callable[[], bytes],
    publish: Callable[[bytes], None],
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stop: Callable[[], bool] = lambda: False,
) -> None:
    trigger = MotionTrigger(cfg.motion.cooldown)
    while not stop():
        active = read_motion()
        if trigger.update(active, clock()):
            log.info("movimiento detectado: sacando foto")
            try:
                jpeg = capture()
            except CaptureError as e:
                log.error("no se pudo sacar la foto: %s", e)
            else:
                publish(jpeg)
                log.info("foto publicada (%d bytes) en %s", len(jpeg), cfg.mqtt.input_topic)
        sleep(cfg.motion.poll_interval)


def run(cfg: Config) -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt.username:
        client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)
    client.on_connect = lambda c, u, f, rc, p: log.info("conectado a MQTT (%s)", rc)
    client.connect(cfg.mqtt.host, cfg.mqtt.port)
    client.loop_start()  # hilo de red: reconecta solo si el broker se reinicia

    read_motion = gpio_reader(cfg.motion)
    log.info("vigilando el PIR en GPIO %d", cfg.motion.pin)
    try:
        loop(
            cfg,
            read_motion,
            capture=lambda: capture_jpeg(cfg.camera),
            publish=lambda jpeg: client.publish(cfg.mqtt.input_topic, jpeg, qos=1),
        )
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="EcoNest: PIR -> foto -> MQTT")
    p.add_argument("--config", help="ruta a config.yaml")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(load_config(args.config))
