from dataclasses import dataclass, field
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
class Config:
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    model: ModelConfig = field(default_factory=ModelConfig)


def load_config(path: str | None = None) -> Config:
    if not path:
        return Config()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return Config(
        mqtt=MqttConfig(**raw.get("mqtt", {})),
        model=ModelConfig(**raw.get("model", {})),
    )
