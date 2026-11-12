import argparse
import logging

from .config import load_config
from .service import run

p = argparse.ArgumentParser(description="EcoNest: servicio YOLO de detección de aves vía MQTT")
p.add_argument("--config", help="ruta a config.yaml")
args = p.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
run(load_config(args.config))
