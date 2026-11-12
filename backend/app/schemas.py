from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
    device_id: str
    timestamp: datetime
    location: Location
    detections: list[BirdDetection]
    count: int = Field(ge=0)
    screenshot: Optional[str] = None  # base64 (JPEG/PNG)


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
    name: str
    zone: str
    lat: float
    lon: float


class DeviceCreated(BaseModel):
    id: str
    token: str  # solo se muestra una vez
