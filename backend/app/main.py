import base64
import binascii
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import Numeric, cast, func, select
from sqlalchemy.orm import Session

from . import config
from .db import Base, engine, get_db
from .limits import BodySizeLimitMiddleware
from .models import Detection, Device
from .schemas import DetectionIn, DetectionOut, DeviceCreate, DeviceCreated
from .security import hash_token, require_admin, require_device

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.validate_settings()  # falla al arrancar si ADMIN_TOKEN falta o es débil
    config.SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)  # MVP: para producción, migrar a Alembic
    yield


app = FastAPI(title="EcoNest API", version="0.1.0", lifespan=lifespan)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=config.MAX_BODY_BYTES)


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------- admin
@app.post("/devices", response_model=DeviceCreated, status_code=201, dependencies=[Depends(require_admin)])
def create_device(body: DeviceCreate, db: Session = Depends(get_db)):
    if db.get(Device, body.id):
        raise HTTPException(409, "Device already exists")
    token = secrets.token_urlsafe(32)
    db.add(Device(**body.model_dump(), token_hash=hash_token(token)))
    db.commit()
    return DeviceCreated(id=body.id, token=token)


# ---------------------------------------------------------------- ingestion
def _save_screenshot(b64: str) -> str:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Screenshot is not valid base64")
    if len(raw) > config.MAX_SCREENSHOT_BYTES:
        raise HTTPException(413, "Screenshot too large")
    if raw.startswith(JPEG_MAGIC):
        ext = "jpg"
    elif raw.startswith(PNG_MAGIC):
        ext = "png"
    else:
        raise HTTPException(422, "Screenshot must be JPEG or PNG")
    name = f"{uuid.uuid4().hex}.{ext}"
    (config.SCREENSHOT_DIR / name).write_bytes(raw)
    return name


@app.post("/detections", response_model=DetectionOut, status_code=201)
def post_detection(body: DetectionIn, device: Device = Depends(require_device), db: Session = Depends(get_db)):
    if body.device_id != device.id:
        raise HTTPException(403, "device_id does not match token")
    shot = _save_screenshot(body.screenshot) if body.screenshot else None
    row = Detection(
        device_id=device.id,
        timestamp=body.timestamp,
        # Ubicación del dispositivo registrado, nunca la del payload.
        zone=device.zone,
        lat=device.lat,
        lon=device.lon,
        count=len(body.detections),
        detections=[d.model_dump(by_alias=True) for d in body.detections],
        screenshot_path=shot,
    )
    db.add(row)
    db.commit()
    return _out(row)


def _out(row: Detection) -> DetectionOut:
    return DetectionOut(
        id=row.id,
        device_id=row.device_id,
        timestamp=row.timestamp,
        zone=row.zone,
        lat=row.lat,
        lon=row.lon,
        count=row.count,
        detections=row.detections,
        screenshot_url=f"/screenshots/{row.id}" if row.screenshot_path else None,
    )


# ------------------------------------------------------------------ queries
def _filters(stmt, zone, device_id, since, until):
    if zone:
        stmt = stmt.where(Detection.zone == zone)
    if device_id:
        stmt = stmt.where(Detection.device_id == device_id)
    if since:
        stmt = stmt.where(Detection.timestamp >= since)
    if until:
        stmt = stmt.where(Detection.timestamp <= until)
    return stmt


@app.get("/detections", response_model=list[DetectionOut])
def list_detections(
    zone: Optional[str] = None,
    device_id: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = _filters(select(Detection), zone, device_id, since, until)
    stmt = stmt.order_by(Detection.timestamp.desc()).limit(limit).offset(offset)
    return [_out(r) for r in db.scalars(stmt)]


def _bucket(granularity: str):
    if engine.dialect.name == "postgresql":
        return func.date_trunc(granularity, Detection.timestamp)
    fmt = "%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d 00:00:00"
    return func.strftime(fmt, Detection.timestamp)


@app.get("/counts")
def counts(
    granularity: Literal["hour", "day"] = "hour",
    zone: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Palomas totales y número de detecciones por zona y franja temporal."""
    bucket = _bucket(granularity).label("bucket")
    stmt = select(bucket, Detection.zone, func.sum(Detection.count), func.count(Detection.id))
    stmt = _filters(stmt, zone, None, since, until)
    stmt = stmt.group_by(bucket, Detection.zone).order_by(bucket)
    return [
        {
            "bucket": b.isoformat() if isinstance(b, datetime) else b,
            "zone": z,
            "total_count": int(total),
            "events": events,
        }
        for b, z, total, events in db.execute(stmt)
    ]


@app.get("/heatmap")
def heatmap(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    precision: int = Query(4, ge=2, le=6),  # 4 decimales ≈ 11 m
    db: Session = Depends(get_db),
):
    """Puntos (lat, lon, peso) agregados en celdas, listos para un mapa de calor."""
    lat = func.round(cast(Detection.lat, Numeric), precision)
    lon = func.round(cast(Detection.lon, Numeric), precision)
    stmt = select(lat, lon, func.sum(Detection.count))
    stmt = _filters(stmt, None, None, since, until).group_by(lat, lon)
    return [{"lat": float(a), "lon": float(o), "weight": int(w)} for a, o, w in db.execute(stmt)]


@app.get("/screenshots/{detection_id}")
def screenshot(detection_id: int, db: Session = Depends(get_db)):
    row = db.get(Detection, detection_id)
    if not row or not row.screenshot_path:
        raise HTTPException(404, "No screenshot")
    return FileResponse(config.SCREENSHOT_DIR / row.screenshot_path)
