from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    zone: Mapped[str] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    detections: Mapped[list["Detection"]] = relationship(back_populates="device")


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (Index("ix_detections_zone_ts", "zone", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    zone: Mapped[str] = mapped_column(String(128))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer)
    # Lista de {class, confidence, bbox}; JSONB en Postgres para poder consultarlo desde Grafana.
    detections: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"))
    screenshot_path: Mapped[str | None] = mapped_column(String(256), nullable=True)

    device: Mapped[Device] = relationship(back_populates="detections")
