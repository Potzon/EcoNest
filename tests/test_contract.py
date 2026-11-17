"""Contrato YOLO -> puente -> backend REAL (FastAPI + SQLite en memoria de tests)."""
import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/contract.db"
os.environ["SCREENSHOT_DIR"] = f"{_tmp}/shots"
os.environ["ADMIN_TOKEN"] = "admin-secret-0123456789"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402
from econest_yolo.config import BackendConfig  # noqa: E402
from econest_yolo.detector import Detection  # noqa: E402
from econest_yolo.messages import build_payload  # noqa: E402
from econest_yolo.uplink import to_backend_payload  # noqa: E402


def test_yolo_message_is_accepted_by_backend():
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), "gray").save(buf, "JPEG")
    jpeg = buf.getvalue()
    yolo_msg = json.loads(build_payload([Detection("bird", 14, 0.87, [10.0, 5.0, 30.0, 25.0])], 64, 48, jpeg))

    with TestClient(app) as c:
        token = c.post(
            "/devices",
            headers={"Authorization": "Bearer admin-secret-0123456789"},
            json={"id": "nest-01", "name": "Farola", "zone": "Doña Casilda", "lat": 43.263, "lon": -2.935},
        ).json()["token"]
        r = c.post(
            "/detections",
            headers={"Authorization": f"Bearer {token}"},
            json=to_backend_payload(yolo_msg, "nest-01"),
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["count"] == 1 and out["zone"] == "Doña Casilda"
        assert out["detections"][0]["bbox"] == [10.0, 5.0, 20.0, 20.0]
        assert c.get(out["screenshot_url"]).content == jpeg


def test_heartbeat_makes_device_online():
    from econest_yolo.heartbeat import Heartbeat

    with TestClient(app) as c:
        token = c.post(
            "/devices",
            headers={"Authorization": "Bearer admin-secret-0123456789"},
            json={"id": "nest-hb", "name": "Farola 2", "zone": "El Arenal", "lat": 43.258, "lon": -2.930},
        ).json()["token"]
        # Sin heartbeat: nunca visto, offline.
        d = next(d for d in c.get("/devices").json() if d["id"] == "nest-hb")
        assert d["last_seen"] is None and d["online"] is False

        hb = Heartbeat(
            BackendConfig(url="", device_id="nest-hb", token=token),
            http=c,  # TestClient como transporte HTTP
        )
        assert hb.beat() is True

        d = next(d for d in c.get("/devices").json() if d["id"] == "nest-hb")
        assert d["online"] is True and d["last_seen"] is not None
        assert d["status"]["cpu_temp_c"] is not None or d["status"]["uptime_s"] is not None
        hist = c.get("/devices/nest-hb/status").json()
        assert len(hist) == 1
