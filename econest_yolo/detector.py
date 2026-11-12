import io
from dataclasses import dataclass

from PIL import Image

from .config import ModelConfig


@dataclass
class Detection:
    class_name: str
    class_id: int
    confidence: float
    bbox_xyxy: list[float]


class BirdDetector:
    def __init__(self, cfg: ModelConfig):
        from ultralytics import YOLO  # import tardío: arranque/tests más ligeros

        self.cfg = cfg
        self.model = YOLO(cfg.weights)

    def detect(self, jpeg_bytes: bytes) -> tuple[list[Detection], int, int]:
        """Devuelve (detecciones, ancho, alto). Lanza ValueError si la imagen es inválida."""
        try:
            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
        except Exception as e:
            raise ValueError(f"imagen no decodificable: {e}") from e
        w, h = img.size
        res = self.model.predict(
            img,
            conf=self.cfg.conf,
            classes=self.cfg.classes,
            device=self.cfg.device,
            verbose=False,
        )[0]
        dets = []
        for b in res.boxes:
            cid = int(b.cls)
            dets.append(
                Detection(
                    class_name=res.names[cid],
                    class_id=cid,
                    confidence=round(float(b.conf), 4),
                    bbox_xyxy=[round(float(v), 1) for v in b.xyxy[0].tolist()],
                )
            )
        return dets, w, h
