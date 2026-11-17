import httpx

from econest_yolo.config import BackendConfig
from econest_yolo.heartbeat import Heartbeat, collect_metrics


def _hb(handler, interval=60.0):
    cfg = BackendConfig(url="http://backend", device_id="nest-01", token="t", heartbeat_interval=interval)
    http = httpx.Client(base_url=cfg.url, transport=httpx.MockTransport(handler))
    return Heartbeat(cfg, http)


def test_beat_ok():
    assert _hb(lambda r: httpx.Response(201, json={})).beat() is True


def test_beat_tolerates_backend_down():
    def boom(request):
        raise httpx.ConnectError("sin red")

    assert _hb(boom).beat() is False  # no lanza; se espera al siguiente latido


def test_beat_reports_rejection():
    assert _hb(lambda r: httpx.Response(401, json={})).beat() is False


def test_beat_sends_only_optional_metrics():
    seen = {}

    def handler(request):
        seen["json"] = request.read()
        return httpx.Response(201, json={})

    _hb(handler).beat()
    # todas las métricas son opcionales; cualquier colección válida sirve
    assert seen["json"]


def test_collect_metrics_keys_are_valid_and_in_range():
    LIMITS = {"cpu_temp_c": (-50, 150), "load_1m": (0, 1000), "mem_used_pct": (0, 100), "disk_used_pct": (0, 100), "uptime_s": (0, None)}
    metrics = collect_metrics()
    for key, value in metrics.items():
        assert key in LIMITS, f"clave inesperada: {key}"
        low, high = LIMITS[key]
        assert value >= low, f"{key}={value} por debajo del mínimo"
        if high is not None:
            assert value <= high, f"{key}={value} por encima del máximo"


def test_clamp_keeps_values_inside_schema():
    from econest_yolo.heartbeat import _clamp

    assert _clamp("cpu_temp_c", -999) == -50
    assert _clamp("cpu_temp_c", 999) == 150
    assert _clamp("load_1m", -1) == 0
    assert _clamp("disk_used_pct", 123.4) == 100.0
    assert _clamp("uptime_s", 1.9) == 1
    assert _clamp("cpu_temp_c", 42.345) == 42.3  # redondeo a 1 decimal
