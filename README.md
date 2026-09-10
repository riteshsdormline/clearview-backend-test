---
title: Clearview Application Backend
emoji: 🌫️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Clearview Backend

FastAPI service behind the Clearview app: dehazes/clears a photo, detects
objects (YOLOv8n), scores each for visible damage/wear, and returns both a
clean enhanced image and an annotated one plus a JSON report.

## Endpoints

- `GET /health` -- liveness check
- `POST /analyze` -- multipart form:
  - `image` (file, required)
  - `threshold` (float, default 0.65) -- scuff-score cutoff for "scuffed"
  - `warn_ratio` (float, default 0.75) -- fraction of threshold for "possible wear"
  - `detector` (`voc` or `regions`, default `voc`) -- kept for backward
    compatibility; `voc` now runs YOLOv8n regardless of the name
  - `max_boxes` (int, default 25)
  - `no_dehaze` (bool, default false)
  - `no_enhance` (bool, default false)
  - `sharpen` (float, default 0.5)

  Returns JSON: `{ report, original_image_base64, original_image_content_type,
  modified_image_base64, annotated_image_base64, processing_seconds }`

See the main project README for the full pipeline breakdown (dehaze.py,
scuff_score.py, enhance.py, detector.py, region_detector.py).
