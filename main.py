"""
Thin HTTP wrapper around pipeline.py. Next.js (or anything else) calls this
over the network instead of needing OpenCV/the models/mobile-incompatible
detector layers running client-side.

Run locally:
    uvicorn main:app --reload --port 8000

Endpoints:
    GET  /health           -- liveness check
    POST /analyze          -- multipart form: image file + options -> JSON report + annotated image
"""
import base64
import json
import os
import shutil
import tempfile
import time

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pipeline import run
from detector import ObjectDetector

app = FastAPI(title="Clearview API", version="1.0.0")

# Tighten allow_origins to your actual frontend domain(s) before going to
# production -- "*" is fine for local development only.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))  # 10MB default
MODEL_DIR = os.environ.get(
    "MODEL_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "models"),
)

# Load the free YOLOv8n detector once at process startup.
_voc_detector = ObjectDetector(model_dir=MODEL_DIR)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(
    image: UploadFile = File(...),
    threshold: float = Form(0.65),
    warn_ratio: float = Form(0.75),
    detector: str = Form("voc"),
    max_boxes: int = Form(25),
    no_dehaze: bool = Form(False),
    no_enhance: bool = Form(False),
    sharpen: float = Form(0.5),
):
    if detector not in ("voc", "regions"):
        raise HTTPException(400, "detector must be 'voc' or 'regions'")

    contents = await image.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image exceeds {MAX_UPLOAD_BYTES} byte limit")

    with tempfile.TemporaryDirectory() as tmp_dir:
        in_path = os.path.join(tmp_dir, image.filename or "input.jpg")
        with open(in_path, "wb") as f:
            f.write(contents)

        start = time.time()
        try:
            out_img_path, out_modified_path, out_json_path, _results = run(
                in_path,
                out_dir=tmp_dir,
                model_dir=MODEL_DIR,
                scuff_threshold=threshold,
                warn_ratio=warn_ratio,
                detector_mode=detector,
                max_boxes=max_boxes,
                auto_dehaze=not no_dehaze,
                enhance=not no_enhance,
                sharpen_strength=sharpen,
                voc_detector=_voc_detector if detector == "voc" else None,
            )
        except Exception as e:
            raise HTTPException(500, f"Processing failed: {e}")
        elapsed = time.time() - start

        with open(out_img_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        with open(out_modified_path, "rb") as f:
            modified_img_b64 = base64.b64encode(f.read()).decode("utf-8")
        report = json.load(open(out_json_path))

    return JSONResponse({
        "report": report,
        "original_image_base64": base64.b64encode(contents).decode("utf-8"),
        "original_image_content_type": image.content_type or "image/jpeg",
        "modified_image_base64": modified_img_b64,
        "annotated_image_base64": img_b64,
        "processing_seconds": round(elapsed, 2),
    })
