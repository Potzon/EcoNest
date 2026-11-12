"""Prueba local sin broker: python scripts/detect_file.py foto.jpg [--config config.yaml]"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from econest_yolo.config import load_config
from econest_yolo.detector import BirdDetector
from econest_yolo.messages import build_payload

p = argparse.ArgumentParser()
p.add_argument("image")
p.add_argument("--config")
a = p.parse_args()

data = Path(a.image).read_bytes()
dets, w, h = BirdDetector(load_config(a.config).model).detect(data)
if not dets:
    print("sin aves")
else:
    import json

    out = json.loads(build_payload(dets, w, h, data))
    out["image_b64"] = f"<{len(data)} bytes>"
    print(json.dumps(out, indent=2))
