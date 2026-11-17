from dataclasses import dataclass
import numpy as np
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

    def detect(self, frame: np.ndarray) -> tuple[list[Detection], int, int]:
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            raise ValueError("frame inválido")

        h, w = frame.shape[:2]

        res = self.model.predict(
            frame,
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
