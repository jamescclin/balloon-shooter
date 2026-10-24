"""氣球偵測，包裝 ai-balloon 訓練出的 YOLO 模型 (.engine / .pt)。"""
from dataclasses import dataclass

from ultralytics import YOLO


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2

    @property
    def cy(self):
        return (self.y1 + self.y2) / 2


class BalloonDetector:
    def __init__(self, model_path, imgsz=640, conf=0.5):
        self.model = YOLO(str(model_path), task="detect")
        self.imgsz = imgsz
        self.conf = conf

    def detect(self, frame):
        """回傳此畫面中所有氣球的 Detection 清單。"""
        result = self.model.predict(frame, imgsz=self.imgsz, conf=self.conf, verbose=False)[0]
        return [
            Detection(x1, y1, x2, y2, conf)
            for (x1, y1, x2, y2), conf in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist())
        ]
