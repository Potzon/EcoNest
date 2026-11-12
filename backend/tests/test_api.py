import base64
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SCREENSHOT_DIR"] = f"{_tmp}/shots"
os.environ["ADMIN_TOKEN"] = "admin-secret-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = {"Authorization": "Bearer admin-secret-0123456789"}
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


def payload(device_id="nest-01", count=1, ts="2026-10-01T10:15:00Z", lat=43.2630, lon=-2.9350, **extra):
    return {
        "device_id": device_id,
        "timestamp": ts,
        "location": {"lat": lat, "lon": lon, "zone": "Doña Casilda"},
        "detections": [{"class": "pigeon", "confidence": 0.91, "bbox": [10, 20, 30, 40]}] * count,
        "count": count,
        **extra,
    }


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    r = client.post("/devices", headers=ADMIN, json={
        "id": "nest-01", "name": "Farola 1", "zone": "Doña Casilda", "lat": 43.263, "lon": -2.935})
    assert r.status_code == 201
    return r.json()["token"]


def test_admin_required(client):
    assert client.post("/devices", json={}).status_code == 401
    assert client.post("/devices", headers={"Authorization": "Bearer nope"}, json={}).status_code == 401


def test_duplicate_device(client, token):
    r = client.post("/devices", headers=ADMIN, json={
        "id": "nest-01", "name": "x", "zone": "z", "lat": 0, "lon": 0})
    assert r.status_code == 409


def test_post_requires_valid_token(client, token):
    assert client.post("/detections", json=payload()).status_code == 401
    assert client.post("/detections", json=payload(), headers={"Authorization": "Bearer bad"}).status_code == 401


def test_device_id_must_match_token(client, token):
    r = client.post("/detections", json=payload(device_id="otro"), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_post_and_get_with_screenshot(client, token):
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/detections", json=payload(count=2, screenshot=JPEG), headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["detections"][0]["class"] == "pigeon"
    assert body["screenshot_url"] == f"/screenshots/{body['id']}"
    shot = client.get(body["screenshot_url"])
    assert shot.status_code == 200 and shot.content.startswith(b"\xff\xd8\xff")


def test_bad_screenshots(client, token):
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/detections", json=payload(screenshot="%%%no-b64"), headers=h).status_code == 422
    not_img = base64.b64encode(b"hello world").decode()
    assert client.post("/detections", json=payload(screenshot=not_img), headers=h).status_code == 422


def test_validation(client, token):
    h = {"Authorization": f"Bearer {token}"}
    bad = payload()
    bad["detections"][0]["confidence"] = 1.7
    assert client.post("/detections", json=bad, headers=h).status_code == 422
    assert client.post("/detections", json=payload(count=-1), headers=h).status_code == 422


def test_list_filters(client, token):
    h = {"Authorization": f"Bearer {token}"}
    client.post("/detections", json=payload(ts="2026-10-02T09:00:00Z"), headers=h)
    all_rows = client.get("/detections").json()
    assert len(all_rows) == 2  # los rechazados (401/403/422) no se guardan
    assert all_rows[0]["timestamp"] >= all_rows[-1]["timestamp"]  # más recientes primero
    only_13 = client.get("/detections", params={"since": "2026-10-02T00:00:00Z"}).json()
    assert len(only_13) == 1
    assert client.get("/detections", params={"zone": "Inexistente"}).json() == []


def test_counts(client):
    daily = client.get("/counts", params={"granularity": "day"}).json()
    by_day = {d["bucket"][:10]: d for d in daily}
    assert by_day["2026-10-01"]["total_count"] == 2
    assert by_day["2026-10-02"]["total_count"] == 1


def test_heatmap(client):
    pts = client.get("/heatmap").json()
    assert pts and pts[0]["lat"] == 43.263 and pts[0]["lon"] == -2.935
    assert sum(p["weight"] for p in pts) == 3


def test_screenshot_404(client):
    assert client.get("/screenshots/99999").status_code == 404


# ----------------------------------------------- el servidor no se fía del cliente
def test_count_must_match_detections(client, token):
    h = {"Authorization": f"Bearer {token}"}
    bad = payload(count=1)
    bad["count"] = 9999
    assert client.post("/detections", json=bad, headers=h).status_code == 422


def test_count_is_optional_and_derived(client, token):
    h = {"Authorization": f"Bearer {token}"}
    body = payload(count=3, ts="2026-10-03T08:00:00Z")
    del body["count"]
    r = client.post("/detections", json=body, headers=h)
    assert r.status_code == 201 and r.json()["count"] == 3


def test_location_comes_from_device_not_payload(client, token):
    h = {"Authorization": f"Bearer {token}"}
    body = payload(ts="2026-10-03T09:00:00Z")
    body["location"] = {"lat": -80, "lon": 100, "zone": "Inventada"}
    r = client.post("/detections", json=body, headers=h)
    assert r.status_code == 201
    out = r.json()
    assert (out["zone"], out["lat"], out["lon"]) == ("Doña Casilda", 43.263, -2.935)


def test_location_is_optional(client, token):
    h = {"Authorization": f"Bearer {token}"}
    body = payload(ts="2026-10-03T10:00:00Z")
    del body["location"]
    assert client.post("/detections", json=body, headers=h).status_code == 201


def test_timestamp_must_be_aware_and_not_future(client, token):
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/detections", json=payload(ts="2026-10-01T10:15:00"), headers=h).status_code == 422
    assert client.post("/detections", json=payload(ts="2099-01-01T00:00:00Z"), headers=h).status_code == 422


def test_timestamp_with_offset_is_normalised_to_utc(client, token):
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/detections", json=payload(ts="2026-10-04T12:00:00+01:00"), headers=h)
    assert r.status_code == 201
    assert r.json()["timestamp"].startswith("2026-10-04T11:00:00")


# ------------------------------------------------------------ punto 2: límites y arranque
from app import config  # noqa: E402


def test_too_many_detections_rejected(client, token):
    h = {"Authorization": f"Bearer {token}"}
    ok = payload(count=config.MAX_DETECTIONS_PER_EVENT, ts="2026-10-05T08:00:00Z")
    assert client.post("/detections", json=ok, headers=h).status_code == 201
    too_many = payload(count=config.MAX_DETECTIONS_PER_EVENT + 1)
    assert client.post("/detections", json=too_many, headers=h).status_code == 422


def test_screenshot_string_too_long_rejected(client, token):
    h = {"Authorization": f"Bearer {token}"}
    huge = "A" * (config.MAX_SCREENSHOT_B64_CHARS + 4)
    assert client.post("/detections", json=payload(screenshot=huge), headers=h).status_code == 422


def test_oversized_body_rejected_before_parsing(client, token):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = client.post("/detections", content=b" " * (config.MAX_BODY_BYTES + 1), headers=h)
    assert r.status_code == 413


def test_chunked_body_without_length_rejected(client, token):
    h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = client.post("/detections", content=iter([b"{}"]), headers=h)
    assert r.status_code == 411


def test_normal_screenshot_still_works_under_limit(client, token):
    h = {"Authorization": f"Bearer {token}"}
    assert client.post("/detections", json=payload(ts="2026-10-05T09:00:00Z", screenshot=JPEG), headers=h).status_code == 201


@pytest.mark.parametrize("bad", ["", "change-me", "Admin", "demasiado-corto"])
def test_app_refuses_to_start_with_missing_or_weak_admin_token(monkeypatch, bad):
    monkeypatch.setattr(config, "ADMIN_TOKEN", bad)
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_device_registration_validates_ranges_and_lengths(client):
    base = {"id": "nest-x", "name": "n", "zone": "z", "lat": 43.0, "lon": -2.9}
    assert client.post("/devices", headers=ADMIN, json={**base, "lat": 999}).status_code == 422
    assert client.post("/devices", headers=ADMIN, json={**base, "lon": -999}).status_code == 422
    assert client.post("/devices", headers=ADMIN, json={**base, "name": "x" * 129}).status_code == 422


# ------------------------------------------------------ punto 3: CORS, estado, heatmap
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import DeviceStatus  # noqa: E402


def test_cors_preflight_allows_configured_origin_only(client):
    ask = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
    ok = client.options("/detections", headers={"Origin": "http://localhost:5173", **ask})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options("/detections", headers={"Origin": "https://evil.example", **ask})
    assert "access-control-allow-origin" not in bad.headers


def test_cors_headers_also_on_error_responses(client):
    r = client.get("/detections", params={"limit": 0}, headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 422
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_status_requires_device_token(client):
    assert client.post("/devices/me/status", json={}).status_code == 401
    assert client.post("/devices/me/status", json={}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_status_post_and_validation(client, token):
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/devices/me/status", headers=h, json={"cpu_temp_c": 51.5, "load_1m": 0.42, "mem_used_pct": 38.0, "uptime_s": 3600})
    assert r.status_code == 201
    assert r.json()["cpu_temp_c"] == 51.5 and r.json()["timestamp"]
    assert client.post("/devices/me/status", headers=h, json={}).status_code == 201  # heartbeat vacío
    assert client.post("/devices/me/status", headers=h, json={"cpu_temp_c": 999}).status_code == 422
    assert client.post("/devices/me/status", headers=h, json={"mem_used_pct": 120}).status_code == 422
    assert client.post("/devices/me/status", headers=h, json={"cpu_temp": 50}).status_code == 422  # campo desconocido


def test_devices_list_shows_online_status_without_secrets(client, token):
    client.post("/devices/me/status", headers={"Authorization": f"Bearer {token}"}, json={"cpu_temp_c": 48.0})
    r = client.get("/devices")
    assert r.status_code == 200
    dev = next(d for d in r.json() if d["id"] == "nest-01")
    assert dev["online"] is True and dev["last_seen"] and dev["status"]["cpu_temp_c"] == 48.0
    assert not any("token" in k for k in dev)


def test_device_without_heartbeat_is_offline(client):
    client.post("/devices", headers=ADMIN, json={"id": "nest-02", "name": "Sin señal", "zone": "Zona B", "lat": 43.3, "lon": -2.9})
    dev = next(d for d in client.get("/devices").json() if d["id"] == "nest-02")
    assert dev["online"] is False and dev["last_seen"] is None and dev["status"] is None


def test_old_heartbeat_means_offline(client):
    client.post("/devices", headers=ADMIN, json={"id": "nest-03", "name": "Caída", "zone": "Zona C", "lat": 43.4, "lon": -2.9})
    old = datetime.now(timezone.utc) - timedelta(seconds=config.ONLINE_THRESHOLD_SECONDS + 60)
    with SessionLocal() as db:
        db.add(DeviceStatus(device_id="nest-03", timestamp=old, cpu_temp_c=70.0))
        db.commit()
    dev = next(d for d in client.get("/devices").json() if d["id"] == "nest-03")
    assert dev["online"] is False and dev["last_seen"] is not None


def test_status_history(client, token):
    h = {"Authorization": f"Bearer {token}"}
    for t in (40.0, 41.0, 42.0):
        client.post("/devices/me/status", headers=h, json={"cpu_temp_c": t})
    hist = client.get("/devices/nest-01/status", params={"limit": 2}).json()
    assert len(hist) == 2
    assert hist[0]["timestamp"] >= hist[1]["timestamp"]  # más reciente primero
    assert client.get("/devices/nest-01/status", params={"since": "2099-01-01T00:00:00Z"}).json() == []
    assert client.get("/devices/no-existe/status").status_code == 404


def test_heatmap_zone_filter(client):
    assert client.get("/heatmap", params={"zone": "Doña Casilda"}).json()
    assert client.get("/heatmap", params={"zone": "Otra zona"}).json() == []
