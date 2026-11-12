import logging

import paho.mqtt.client as mqtt

from .config import Config
from .detector import BirdDetector
from .messages import build_payload

log = logging.getLogger("econest_yolo")


def run(cfg: Config) -> None:
    detector = BirdDetector(cfg.model)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if cfg.mqtt.username:
        client.username_pw_set(cfg.mqtt.username, cfg.mqtt.password)

    def on_connect(c, userdata, flags, reason_code, properties):
        log.info("conectado a MQTT (%s), suscrito a %s", reason_code, cfg.mqtt.input_topic)
        c.subscribe(cfg.mqtt.input_topic)

    def on_message(c, userdata, msg):
        try:
            dets, w, h = detector.detect(msg.payload)
        except ValueError as e:
            log.warning("mensaje descartado: %s", e)
            return
        if not dets:
            log.info("sin aves")
            return
        c.publish(cfg.mqtt.output_topic, build_payload(dets, w, h, msg.payload))
        log.info("publicadas %d detecciones", len(dets))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(cfg.mqtt.host, cfg.mqtt.port)
    client.loop_forever()
