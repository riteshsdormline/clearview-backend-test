import base64
import json
import os
import tempfile
import time
import gc
import cv2
import gradio as gr
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pipeline import run
from detector import ObjectDetector

# 1. Setup FastAPI (for the Flutter app)
app = FastAPI(title="Clearview API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
_voc_detector = ObjectDetector(model_dir=MODEL_DIR)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze_api(
    image: UploadFile = File(...),
    threshold: float = Form(0.65),
    detector: str = Form("voc"),
):
    contents = await image.read()
    with tempfile.TemporaryDirectory() as tmp_dir:
        in_path = os.path.join(tmp_dir, "input.jpg")
        with open(in_path, "wb") as f:
            f.write(contents)

        out_img_path, out_modified_path, out_json_path, _results = run(
            in_path,
            out_dir=tmp_dir,
            model_dir=MODEL_DIR,
            scuff_threshold=threshold,
            detector_mode=detector,
            voc_detector=_voc_detector,
        )

        with open(out_img_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        with open(out_modified_path, "rb") as f:
            modified_img_b64 = base64.b64encode(f.read()).decode("utf-8")
        report = json.load(open(out_json_path))

    gc.collect()
    return JSONResponse({
        "report": report,
        "modified_image_base64": modified_img_b64,
        "annotated_image_base64": img_b64,
    })

# 2. Setup Gradio (for the Web UI and HF compatibility)
def gradio_analyze(image_np, threshold):
    if image_np is None:
        return None, None, "Please upload an image"

    with tempfile.TemporaryDirectory() as tmp_dir:
        in_path = os.path.join(tmp_dir, "input.jpg")
        cv2.imwrite(in_path, cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR))

        out_img_path, out_modified_path, out_json_path, _ = run(
            in_path,
            out_dir=tmp_dir,
            model_dir=MODEL_DIR,
            scuff_threshold=threshold,
            voc_detector=_voc_detector,
        )

        ann_img = cv2.cvtColor(cv2.imread(out_img_path), cv2.COLOR_BGR2RGB)
        mod_img = cv2.cvtColor(cv2.imread(out_modified_path), cv2.COLOR_BGR2RGB)
        report = json.load(open(out_json_path))

    return mod_img, ann_img, json.dumps(report, indent=2)

demo = gr.Interface(
    fn=gradio_analyze,
    inputs=[gr.Image(), gr.Slider(0.1, 0.9, value=0.65, label="Threshold")],
    outputs=[gr.Image(label="Enhanced"), gr.Image(label="Annotated"), gr.Code(label="Report", language="json")],
    title="Clearview Visual Analysis",
    description="Backend API is running. You can also test it here."
)

# 3. Mount Gradio into FastAPI
# This keeps the API at the root and puts the UI at /
app = gr.mount_fastapi(app, demo, path="/")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
