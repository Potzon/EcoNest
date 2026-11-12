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


@dataclass
class Config:
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)


def load_config(path: str | None = None) -> Config:
    cfg = Config()
    if path:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        cfg = Config(
            mqtt=MqttConfig(**raw.get("mqtt", {})),
            model=ModelConfig(**raw.get("model", {})),
            backend=BackendConfig(**raw.get("backend", {})),
        )
    # El token no debería vivir en el YAML: la variable de entorno manda.
    cfg.backend.token = os.getenv("ECONEST_DEVICE_TOKEN") or cfg.backend.token
    return cfg
