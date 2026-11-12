import base64
import json
from datetime import datetime, timezone

from .detector import Detection


def build_payload(dets: list[Detection], width: int, height: int, jpeg_bytes: bytes) -> str:
    return json.dumps(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image_width": width,
            "image_height": height,
            "detections": [
                {
                    "class": d.class_name,
                    "class_id": d.class_id,
                    "confidence": d.confidence,
                    "bbox_xyxy": d.bbox_xyxy,
                }
                for d in dets
            ],
            "image_b64": base64.b64encode(jpeg_bytes).decode("ascii"),
        }
    )
