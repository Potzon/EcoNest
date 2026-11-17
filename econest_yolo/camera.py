"""Captura de una foto JPEG desde una webcam V4L2 usando ffmpeg."""
import logging
import os
import subprocess

from .config import CameraConfig

log = logging.getLogger("econest_yolo.camera")


class CaptureError(RuntimeError):
    pass


def ffmpeg_command(cfg: CameraConfig) -> list[str]:
    """Una sola imagen JPEG por stdout, descartando los primeros fotogramas."""
    return [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "v4l2", "-video_size", cfg.size, "-i", cfg.device,
        "-vf", f"select=gte(n\\,{cfg.warmup_frames})",
        "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "-q:v", "3",
        "pipe:1",
    ]  # fmt: skip


def capture_jpeg(cfg: CameraConfig) -> bytes:
    env = dict(os.environ)
    if cfg.v4l2convert and os.path.exists(cfg.v4l2convert):
        env["LD_PRELOAD"] = cfg.v4l2convert
    try:
        r = subprocess.run(ffmpeg_command(cfg), capture_output=True, timeout=cfg.timeout, env=env)
    except subprocess.TimeoutExpired as e:
        raise CaptureError(f"ffmpeg tardó más de {cfg.timeout}s") from e
    except FileNotFoundError as e:
        raise CaptureError("ffmpeg no está instalado") from e
    jpeg = r.stdout
    if not jpeg.startswith(b"\xff\xd8"):
        err = r.stderr.decode(errors="replace").strip()[-300:]
        raise CaptureError(f"ffmpeg no devolvió un JPEG (código {r.returncode}): {err}")
    return jpeg
