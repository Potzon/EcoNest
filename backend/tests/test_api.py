import base64
import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["SCREENSHOT_DIR"] = f"{_tmp}/shots"
os.environ["ADMIN_TOKEN"] = "admin-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = {"Authorization": "Bearer admin-secret"}
JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


def payload(device_id="nest-01", count=1, ts="2026-11-12T10:15:00Z", lat=43.2630, lon=-2.9350, **extra):
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
    client.post("/detections", json=payload(ts="2026-11-13T09:00:00Z"), headers=h)
    all_rows = client.get("/detections").json()
    assert len(all_rows) == 2  # los rechazados (401/403/422) no se guardan
    assert all_rows[0]["timestamp"] >= all_rows[-1]["timestamp"]  # más recientes primero
    only_13 = client.get("/detections", params={"since": "2026-11-13T00:00:00Z"}).json()
    assert len(only_13) == 1
    assert client.get("/detections", params={"zone": "Inexistente"}).json() == []


def test_counts(client):
    daily = client.get("/counts", params={"granularity": "day"}).json()
    by_day = {d["bucket"][:10]: d for d in daily}
    assert by_day["2026-11-12"]["total_count"] == 2
    assert by_day["2026-11-13"]["total_count"] == 1


def test_heatmap(client):
    pts = client.get("/heatmap").json()
    assert pts and pts[0]["lat"] == 43.263 and pts[0]["lon"] == -2.935
    assert sum(p["weight"] for p in pts) == 3


def test_screenshot_404(client):
    assert client.get("/screenshots/99999").status_code == 404
