import subprocess

from econest_yolo import camera
from econest_yolo.camera import CaptureError, capture_jpeg
from econest_yolo.config import CameraConfig, Config, MotionConfig
from econest_yolo.motion import MotionTrigger, loop

JPEG = b"\xff\xd8\xff" + b"0" * 10


def test_trigger_fires_on_motion_and_respects_cooldown():
    t = MotionTrigger(cooldown=5)
    assert t.update(False, 0) is False
    assert t.update(True, 1) is True  # empieza el movimiento
    assert t.update(True, 2) is False  # dentro del cooldown
    assert t.update(True, 6) is True  # sigue habiendo movimiento: otra foto
    assert t.update(False, 7) is False
    assert t.update(True, 8) is False  # nuevo movimiento, pero aún en cooldown
    assert t.update(True, 11) is True


def test_loop_captures_and_publishes_once_per_motion():
    cfg = Config(motion=MotionConfig(cooldown=5, poll_interval=1))
    levels = iter([False, True, True, False, False])
    now = iter(range(100))
    published: list[bytes] = []
    pending = [5]  # número de iteraciones

    def stop():
        pending[0] -= 1
        return pending[0] < 0

    loop(cfg, lambda: next(levels), lambda: JPEG, published.append,
         clock=lambda: next(now), sleep=lambda s: None, stop=stop)  # fmt: skip
    assert published == [JPEG]


def test_loop_survives_camera_errors():
    cfg = Config(motion=MotionConfig(cooldown=0, poll_interval=0))
    published: list[bytes] = []
    calls = iter([CaptureError("sin cámara"), JPEG])

    def capture():
        r = next(calls)
        if isinstance(r, Exception):
            raise r
        return r

    pending = [2]

    def stop():
        pending[0] -= 1
        return pending[0] < 0

    loop(cfg, lambda: True, capture, published.append, sleep=lambda s: None, stop=stop)
    assert published == [JPEG]


def test_capture_rejects_non_jpeg(monkeypatch):
    def fake_run(cmd, **kw):
        assert cmd[0] == "ffmpeg" and "/dev/video0" in cmd
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"No such device")

    monkeypatch.setattr(camera.subprocess, "run", fake_run)
    try:
        capture_jpeg(CameraConfig(v4l2convert=None))
    except CaptureError as e:
        assert "No such device" in str(e)
    else:
        raise AssertionError("debería fallar")


def test_capture_returns_jpeg(monkeypatch):
    monkeypatch.setattr(
        camera.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=JPEG, stderr=b"")
    )
    assert capture_jpeg(CameraConfig(v4l2convert=None)) == JPEG
