"""
Class-agnostic object region proposals via OpenCV Selective Search.

Unlike detector.py's semantic YOLO model, this doesn't need to know in
advance what kinds of products you're photographing. It proposes candidate
object regions ("this looks like a distinct object") using classical
segmentation (color/texture/size similarity merging).
This is the right fit for a shelf/pile of mixed, arbitrary product types
where a fixed-class detector would just silently miss anything outside its
training classes.

Trade-off vs. detector.py: proposals are shape/color/texture-based, not
semantic, so you'll get some regions that aren't real objects (a shadow, a
shelf edge, a gap between items). The area/aspect-ratio filters and NMS
below cut most of that out, but expect more noise than a trained detector
-- tune the constructor args against your actual shelf photos.
"""
import cv2
import numpy as np


class RegionProposalDetector:
    def __init__(self, max_proposals=400, top_k=25, min_area_frac=0.01,
                 max_area_frac=0.6, min_aspect=0.2, max_aspect=5.0,
                 nms_iou=0.3, quality=False):
        """
        max_proposals: how many raw proposals Selective Search generates
            before filtering (higher = slower, more thorough).
        top_k: max number of object boxes kept after filtering + NMS --
            keeps the report readable and bounds per-image runtime.
        min_area_frac / max_area_frac: reject boxes smaller/larger than
            this fraction of total image area (cuts tiny noise regions and
            whole-background boxes).
        min_aspect / max_aspect: reject extremely thin/wide slivers.
        nms_iou: overlap threshold for de-duplicating overlapping proposals
            of the same object.
        quality: True uses Selective Search's slower "quality" mode
            (better recall, especially on cluttered shelves) instead of
            "fast" mode.
        """
        self.max_proposals = max_proposals
        self.top_k = top_k
        self.min_area_frac = min_area_frac
        self.max_area_frac = max_area_frac
        self.min_aspect = min_aspect
        self.max_aspect = max_aspect
        self.nms_iou = nms_iou
        self.quality = quality

    def detect(self, image_bgr):
        """
        Returns the same shape of result as detector.py's ObjectDetector,
        so it's a drop-in swap in pipeline.py:
            [{"box": (x1,y1,x2,y2), "label": "object", "confidence": 1.0}, ...]
        `label` is a placeholder because this stage is deliberately
        class-agnostic.
        """
        h, w = image_bgr.shape[:2]
        img_area = h * w

        ss = cv2.ximgproc.segmentation.createSelectiveSearchSegmentation()
        ss.setBaseImage(image_bgr)
        if self.quality:
            ss.switchToSelectiveSearchQuality()
        else:
            ss.switchToSelectiveSearchFast()
        rects = ss.process()[: self.max_proposals]

        boxes = []
        for (x, y, rw, rh) in rects:
            area_frac = (rw * rh) / img_area
            if area_frac < self.min_area_frac or area_frac > self.max_area_frac:
                continue
            aspect = rw / float(rh) if rh > 0 else 0
            if aspect < self.min_aspect or aspect > self.max_aspect:
                continue
            boxes.append((x, y, x + rw, y + rh))

        # Selective Search already returns proposals in roughly descending
        # "object-like-ness" order, so plain order-preserving NMS is a
        # reasonable de-dup without needing per-box confidence scores.
        boxes = self._nms(boxes, self.nms_iou)[: self.top_k]

        return [
            {"box": (int(x1), int(y1), int(x2), int(y2)), "label": "object", "confidence": 1.0}
            for (x1, y1, x2, y2) in boxes
        ]

    @staticmethod
    def _nms(boxes, iou_thresh):
        if not boxes:
            return []
        boxes_arr = np.array(boxes, dtype=np.float32)
        x1, y1, x2, y2 = boxes_arr[:, 0], boxes_arr[:, 1], boxes_arr[:, 2], boxes_arr[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = np.arange(len(boxes))
        keep = []
        while len(order) > 0:
            i = order[0]
            keep.append(i)
            if len(order) == 1:
                break
            rest = order[1:]
            xx1 = np.maximum(x1[i], x1[rest])
            yy1 = np.maximum(y1[i], y1[rest])
            xx2 = np.minimum(x2[i], x2[rest])
            yy2 = np.minimum(y2[i], y2[rest])
            w_ = np.maximum(0, xx2 - xx1)
            h_ = np.maximum(0, yy2 - yy1)
            inter = w_ * h_
            iou = inter / (areas[i] + areas[rest] - inter + 1e-6)
            order = rest[iou <= iou_thresh]
        return [tuple(boxes[i]) for i in keep]
