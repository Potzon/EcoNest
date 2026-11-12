import base64

import httpx

from econest_yolo.config import BackendConfig
from econest_yolo.uplink import Uplink, to_backend_payload

MSG = {
    "timestamp": "2026-10-01T10:15:00+00:00",
    "image_width": 640,
    "image_height": 480,
    "detections": [{"class": "bird", "class_id": 14, "confidence": 0.87, "bbox_xyxy": [100.0, 50.0, 160.0, 90.0]}],
    "image_b64": base64.b64encode(b"\xff\xd8\xff" + b"0" * 10).decode(),
}


def test_translation_to_backend_contract():
    out = to_backend_payload(MSG, "nest-01")
    assert out["device_id"] == "nest-01"
    assert out["timestamp"] == MSG["timestamp"]
    assert out["detections"] == [{"class": "bird", "confidence": 0.87, "bbox": [100.0, 50.0, 60.0, 40.0]}]
    assert out["screenshot"] == MSG["image_b64"]
    assert "count" not in out and "location" not in out  # los deriva el backend


def test_oversized_screenshot_is_dropped_not_the_detection():
    out = to_backend_payload(MSG, "nest-01", max_screenshot_bytes=5)
    assert "screenshot" not in out and out["detections"]


def _uplink(handler):
    cfg = BackendConfig(url="http://backend", device_id="nest-01", token="t")
    http = httpx.Client(base_url=cfg.url, transport=httpx.MockTransport(handler))
    return Uplink(cfg, http)


def test_send_ok_and_retry_rules():
    assert _uplink(lambda r: httpx.Response(201, json={"id": 1})).send(MSG) is True
    assert _uplink(lambda r: httpx.Response(500)).send(MSG) is False  # reintentar
    assert _uplink(lambda r: httpx.Response(429)).send(MSG) is False  # reintentar
    assert _uplink(lambda r: httpx.Response(401, json={})).send(MSG) is True  # no reintentar
    assert _uplink(lambda r: httpx.Response(422, json={})).send(MSG) is True


def test_send_retries_when_network_down():
    def boom(request):
        raise httpx.ConnectError("sin red")

    assert _uplink(boom).send(MSG) is False


def test_malformed_message_is_discarded():
    assert _uplink(lambda r: httpx.Response(201, json={"id": 1})).send({"foo": 1}) is True


def test_queue_is_bounded():
    cfg = BackendConfig(url="http://b", device_id="d", token="t", queue_size=2)
    u = Uplink(cfg, httpx.Client(base_url=cfg.url))
    for _ in range(5):
        u.submit(MSG)
    assert u.queue.qsize() == 2
