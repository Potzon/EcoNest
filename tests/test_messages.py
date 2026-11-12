import base64
import json

from econest_yolo.detector import Detection
from econest_yolo.messages import build_payload


def test_payload_format():
    d = Detection("bird", 14, 0.87, [1.0, 2.0, 30.0, 40.0])
    out = json.loads(build_payload([d], 640, 480, b"jpegbytes"))
    assert out["image_width"] == 640 and out["image_height"] == 480
    assert out["detections"][0] == {
        "class": "bird", "class_id": 14, "confidence": 0.87, "bbox_xyxy": [1.0, 2.0, 30.0, 40.0]
    }
    assert base64.b64decode(out["image_b64"]) == b"jpegbytes"
    assert "timestamp" in out
