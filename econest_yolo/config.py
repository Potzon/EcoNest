from dataclasses import dataclass, field
import os

import yaml


@dataclass
class MqttConfig:
    host: str = "localhost"
    port: int = 1883
    username: str | None = None
    password: str | None = None
    input_topic: str = "econest/camera/image"
    output_topic: str = "econest/detections"


@dataclass
class ModelConfig:
    weights: str = "yolo11n.pt"
    conf: float = 0.25
    classes: list[int] = field(default_factory=lambda: [14])
    device: str = "cpu"


@dataclass
class BackendConfig:
    """Envío de detecciones al backend REST. Si `url` es None, no se envía nada."""

    url: str | None = None  # p. ej. https://econest.example.org
    device_id: str | None = None  # el id registrado con POST /devices
    token: str | None = None  # mejor por entorno: ECONEST_DEVICE_TOKEN
    timeout: float = 10.0
    queue_size: int = 100  # detecciones pendientes si el backend no responde
    max_screenshot_bytes: int = 2_000_000  # igual que MAX_SCREENSHOT_BYTES del backend
    heartbeat_interval: float = 60.0  # s entre latidos; el backend considera online < 180 s


@dataclass
class MotionConfig:
    """Sensor PIR. El puerto Grove D24 es el GPIO 24 (BCM)."""

    pin: int = 24
    active_high: bool = True  # el PIR de Grove pone la salida a 1 al detectar
    poll_interval: float = 0.05  # segundos entre lecturas del pin
    cooldown: float = 5.0  # mínimo entre fotos; si el PIR sigue a 1, otra foto cada `cooldown`


@dataclass
class CameraConfig:
    """Captura con ffmpeg desde una webcam V4L2 (/dev/videoN)."""

    device: str = "/dev/video0"
    size: str = "352x288"  # resoluciones de la Logitech QuickCam Chat: 320x240 o 352x288
    warmup_frames: int = 10  # se descartan: los primeros salen oscuros mientras ajusta la exposición
    timeout: float = 15.0
    # La QuickCam entrega un formato propio (S561) que ffmpeg no sabe decodificar;
    # libv4l2 lo convierte. Vacío si la cámara da YUYV/MJPEG.
    v4l2convert: str | None = "/usr/lib/aarch64-linux-gnu/libv4l/v4l2convert.so"


@dataclass
class Config:
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    motion: MotionConfig = field(default_factory=MotionConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)


def load_config(path: str | None = None) -> Config:
    cfg = Config()
    if path:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        cfg = Config(
            mqtt=MqttConfig(**raw.get("mqtt", {})),
            model=ModelConfig(**raw.get("model", {})),
            backend=BackendConfig(**raw.get("backend", {})),
            motion=MotionConfig(**raw.get("motion", {})),
            camera=CameraConfig(**raw.get("camera", {})),
        )
    # El token no debería vivir en el YAML: la variable de entorno manda.
    cfg.backend.token = os.getenv("ECONEST_DEVICE_TOKEN") or cfg.backend.token
    return cfg
