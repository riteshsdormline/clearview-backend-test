"""YOLOv8n object detection through the free Ultralytics package."""
from ultralytics import YOLO


class ObjectDetector:
    def __init__(self, model_dir="models", conf_threshold=0.35, model_name="yolov8n.pt"):
        # Ultralytics downloads the small public weight file on first startup
        # and caches it in the container. No API key or paid service is used.
        self.model = YOLO(model_name)
        self.conf_threshold = conf_threshold

    def detect(self, image_bgr):
        """
        Returns a list of dicts: {box: (x1,y1,x2,y2), label: str, confidence: float}
        """
        results = []
        prediction = self.model.predict(source=image_bgr, conf=self.conf_threshold, verbose=False)[0]
        names = prediction.names
        for box in prediction.boxes:
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = box.xyxy[0].int().tolist()
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(prediction.orig_shape[1] - 1, x2), min(prediction.orig_shape[0] - 1, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            results.append({
                "box": (x1, y1, x2, y2),
                "label": names[int(box.cls[0])],
                "confidence": confidence,
            })
        return results
