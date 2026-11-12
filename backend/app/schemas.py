from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from . import config


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    zone: str = Field(min_length=1, max_length=128)


class BirdDetection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cls: str = Field(alias="class", max_length=64)
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)  # [x, y, w, h]


class DetectionIn(BaseModel):
    device_id: str = Field(min_length=1, max_length=64)
    # Obligatoriamente con zona horaria (p. ej. "2026-11-12T10:15:00Z"); se normaliza a UTC.
    timestamp: AwareDatetime
    # Se acepta por compatibilidad con el cliente, pero se IGNORA: la ubicación
    # es la del dispositivo registrado, no la que declare el payload.
    location: Optional[Location] = None
    detections: list[BirdDetection] = Field(max_length=config.MAX_DETECTIONS_PER_EVENT)
    # Opcional: si se envía debe coincidir con len(detections); si no, se calcula.
    count: Optional[int] = Field(default=None, ge=0)
    screenshot: Optional[str] = Field(default=None, max_length=config.MAX_SCREENSHOT_B64_CHARS)  # base64 (JPEG/PNG)

    @model_validator(mode="after")
    def _check(self):
        if self.count is not None and self.count != len(self.detections):
            raise ValueError(f"count ({self.count}) must equal len(detections) ({len(self.detections)})")
        limit = datetime.now(timezone.utc) + timedelta(seconds=config.MAX_FUTURE_SKEW_SECONDS)
        if self.timestamp > limit:
            raise ValueError("timestamp is in the future")
        self.timestamp = self.timestamp.astimezone(timezone.utc)
        return self


class DetectionOut(BaseModel):
    id: int
    device_id: str
    timestamp: datetime
    zone: str
    lat: float
    lon: float
    count: int
    detections: list[dict]
    screenshot_url: Optional[str] = None


class DeviceCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[\w-]+$")
    name: str = Field(min_length=1, max_length=128)
    zone: str = Field(min_length=1, max_length=128)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DeviceCreated(BaseModel):
    id: str
    token: str  # solo se muestra una vez
