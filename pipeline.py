"""
End-to-end pipeline:
  image -> detect objects -> score each for "scuffed-ness" ->
  highlight scuffed objects on the FULL, clear image (nothing is blacked
  out) -> identify what each scuffed object likely is -> save annotated
  output + JSON report.

Usage:
    python pipeline.py --image path/to/photo.jpg --threshold 0.65

Output:
    outputs/<name>_annotated.jpg   -- full clear image, scuffed objects
                                       boxed red, borderline objects boxed
                                       amber, optionally clarity-enhanced
    outputs/<name>_report.json     -- structured results for every detection

v2 changes from the original:
  - Removed the "gray out everything except scuffed boxes" masking. At a
    strict threshold that flags nothing, that produced an almost-black
    output image -- confusing and not what most people want. The image is
    now always shown in full, clear color.
  - Single hard threshold replaced with two tiers (SCUFFED / POSSIBLE) so
    raising the threshold to cut false positives doesn't make borderline
    objects disappear entirely -- they just get a softer amber indicator
    instead of vanishing.
  - Optional whole-image clarity enhancement (denoise + local contrast +
    sharpen) via enhance.py, on by default.
"""
import argparse
import json
import os

import cv2
import numpy as np

from detector import ObjectDetector
from region_detector import RegionProposalDetector
from scuff_score import compute_scuff_score
from enhance import enhance_image
from dehaze import dehaze, auto_brightness, estimate_haze_level


def classify_severity(score, scuff_threshold, warn_ratio=0.75):
    """
    Two-tier read of the scuff score instead of one hard cutoff:
      >= scuff_threshold          -> "scuffed"  (red)
      >= scuff_threshold*warn_ratio -> "possible" (amber)
      else                        -> "ok"        (no box)
    warn_ratio controls how wide the amber band is below your main
    threshold; 0.75 means the amber band starts at 75% of the threshold.
    """
    warn_threshold = scuff_threshold * warn_ratio
    if score >= scuff_threshold:
        return "scuffed"
    if score >= warn_threshold:
        return "possible"
    return "ok"


SEVERITY_COLOR = {
    "scuffed": (0, 0, 255),   # red (BGR)
    "possible": (0, 165, 255),  # amber (BGR)
}
SEVERITY_LABEL_PREFIX = {
    "scuffed": "SCUFFED",
    "possible": "possible wear",
}


def annotate(output, detections, results):
    """
    Draws tiered boxes over the full, untouched image. Objects rated "ok"
    get no box at all, so a clean image stays visually clean.
    """
    for det, res in zip(detections, results):
        severity = res["severity"]
        if severity == "ok":
            continue

        x1, y1, x2, y2 = det["box"]
        color = SEVERITY_COLOR[severity]
        thickness = 3 if severity == "scuffed" else 2
        style_gap = 0 if severity == "scuffed" else 6  # dashed look for "possible"

        if style_gap == 0:
            cv2.rectangle(output, (x1, y1), (x2, y2), color, thickness)
        else:
            _draw_dashed_rect(output, (x1, y1), (x2, y2), color, thickness, style_gap)

        prefix = SEVERITY_LABEL_PREFIX[severity]
        label = f"{prefix}: {res['best_guess']} ({res['scuff_score']:.2f})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        label_y1 = max(0, y1 - th - 8)
        cv2.rectangle(output, (x1, label_y1), (x1 + tw + 6, y1), color, -1)
        cv2.putText(output, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 1, cv2.LINE_AA)

    _draw_legend(output)
    return output


def _draw_dashed_rect(img, pt1, pt2, color, thickness, gap):
    x1, y1 = pt1
    x2, y2 = pt2
    for x in range(x1, x2, gap * 2):
        cv2.line(img, (x, y1), (min(x + gap, x2), y1), color, thickness)
        cv2.line(img, (x, y2), (min(x + gap, x2), y2), color, thickness)
    for y in range(y1, y2, gap * 2):
        cv2.line(img, (x1, y), (x1, min(y + gap, y2)), color, thickness)
        cv2.line(img, (x2, y), (x2, min(y + gap, y2)), color, thickness)


def _draw_legend(img):
    h, w = img.shape[:2]
    x0, y0 = 10, h - 55
    cv2.rectangle(img, (x0 - 6, y0 - 10), (x0 + 230, y0 + 40), (0, 0, 0), -1)
    cv2.rectangle(img, (x0 - 6, y0 - 10), (x0 + 230, y0 + 40), (255, 255, 255), 1)
    cv2.rectangle(img, (x0, y0), (x0 + 18, y0 + 14), SEVERITY_COLOR["scuffed"], -1)
    cv2.putText(img, "scuffed", (x0 + 24, y0 + 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.rectangle(img, (x0, y0 + 20), (x0 + 18, y0 + 34), SEVERITY_COLOR["possible"], -1)
    cv2.putText(img, "possible wear", (x0 + 24, y0 + 32), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (255, 255, 255), 1, cv2.LINE_AA)


def run(image_path, out_dir="outputs", model_dir="models",
        scuff_threshold=0.65, warn_ratio=0.75, detect_conf=0.35, top_k_ids=3,
        enhance=True, denoise_strength=3, clahe_clip=2.0, sharpen_strength=0.5,
        detector_mode="voc", max_boxes=25, always_identify=True,
        region_quality=False, auto_dehaze=True, dehaze_haze_threshold=0.25,
        dehaze_strength=1.0, brightness_target=115,
        voc_detector=None, region_detector=None):
    """
    voc_detector / region_detector: pass pre-constructed
    instances (e.g. loaded once at server startup) to skip re-parsing the
    Caffe model files from disk on every call -- matters a lot in a web
    service context where this otherwise reloads ~60MB of model weights
    per request. CLI usage (pipeline.py run directly) still works fine
    without passing these; they're built fresh as before.
    """
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    # Memory safety: Resize if image is extremely large to prevent OOM on
    # small server instances (e.g. Render free tier 512MB limit).
    h, w = image.shape[:2]
    max_dim = 1000
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    # Dehaze first, before detection/scoring/identification -- everything
    # downstream works on the clearer image, not just the final display.
    # Auto-skipped on already-clear photos (haze level below threshold) so
    # this doesn't distort normal, non-hazy product photos.
    haze_level = estimate_haze_level(image)
    did_dehaze = auto_dehaze and haze_level >= dehaze_haze_threshold
    working_image = image
    if did_dehaze:
        working_image = dehaze(image, strength=dehaze_strength)
        working_image = auto_brightness(working_image, target_mean=brightness_target)

    if detector_mode == "regions":
        # Class-agnostic: fits arbitrary/mixed product types (shoes, phones,
        # furniture, whatever else) that a fixed 20-class VOC model can't
        # name at all. Noisier than the VOC detector on general real-world
        # photos (backgrounds, foliage, sky get proposed as "objects" too)
        # -- prefer this only when your photos genuinely contain mixed,
        # non-VOC-class items. See region_detector.py.
        detector = region_detector or RegionProposalDetector(top_k=max_boxes, quality=region_quality)
    else:
        detector = voc_detector or ObjectDetector(model_dir=model_dir, conf_threshold=detect_conf)
    detections = detector.detect(working_image)

    results = []
    for det in detections:
        x1, y1, x2, y2 = det["box"]
        crop = working_image[y1:y2, x1:x2]
        scuff_info = compute_scuff_score(crop)
        severity = classify_severity(scuff_info["scuff_score"], scuff_threshold, warn_ratio)
        is_scuffed = severity == "scuffed"

        entry = {
            "detector_label": det["label"],
            "detector_confidence": round(det["confidence"], 4),
            "box": det["box"],
            **scuff_info,
            "severity": severity,
            "is_scuffed": is_scuffed,  # kept for backward compatibility
        }

        entry["best_guess"] = det["label"]

        results.append(entry)

    # Whole image, always kept fully visible/clear -- no more blackout mask.
    # Start from the (possibly dehazed) working image so the final output
    # reflects the clarity fix too, not just detection/scoring.
    output_img = working_image.copy()
    if enhance:
        output_img = enhance_image(
            output_img,
            denoise_strength=denoise_strength,
            clahe_clip=clahe_clip,
            sharpen_strength=sharpen_strength,
        )
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(image_path))[0]
    out_modified_path = os.path.join(out_dir, f"{base}_modified.jpg")
    out_img_path = os.path.join(out_dir, f"{base}_annotated.jpg")
    out_json_path = os.path.join(out_dir, f"{base}_report.json")

    cv2.imwrite(out_modified_path, output_img)
    output_img = annotate(output_img, detections, results)
    cv2.imwrite(out_img_path, output_img)
    with open(out_json_path, "w") as f:
        json.dump({
            "source_image": image_path,
            "haze_level": round(haze_level, 4),
            "dehazed": did_dehaze,
            "scuff_threshold": scuff_threshold,
            "warn_threshold": round(scuff_threshold * warn_ratio, 4),
            "num_objects_detected": len(detections),
            "num_scuffed": sum(1 for r in results if r["severity"] == "scuffed"),
            "num_possible": sum(1 for r in results if r["severity"] == "possible"),
            "detections": results,
        }, f, indent=2)

    return out_img_path, out_modified_path, out_json_path, results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect and identify scuffed objects in an image.")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument("--out_dir", default="outputs")
    parser.add_argument("--model_dir", default="models")
    parser.add_argument("--threshold", type=float, default=0.65,
                         help="Scuff score threshold (0-1) above which an object is flagged 'scuffed'")
    parser.add_argument("--warn_ratio", type=float, default=0.75,
                         help="Fraction of --threshold above which an object is flagged 'possible wear' "
                              "instead of disappearing entirely")
    parser.add_argument("--detect_conf", type=float, default=0.35,
                         help="Minimum detector confidence to consider a box")
    parser.add_argument("--no_enhance", action="store_true",
                         help="Skip the denoise/contrast/sharpen clarity pass")
    parser.add_argument("--sharpen", type=float, default=0.5,
                         help="Sharpen strength, 0 disables. ~0.3-0.8 looks natural")
    parser.add_argument("--detector", choices=["voc", "regions"], default="voc",
                         help="'voc' (default): the original fixed 20-class model -- clean, "
                              "reliable boxes but only person/car/chair/etc, no shoe/phone. "
                              "'regions': class-agnostic Selective Search for arbitrary/mixed "
                              "product types, but noisier on general photos.")
    parser.add_argument("--max_boxes", type=int, default=25,
                         help="Cap on number of object regions per image (regions mode)")
    parser.add_argument("--region_quality", action="store_true",
                         help="Use Selective Search 'quality' mode (slower, better recall on "
                              "cluttered shelf photos) instead of 'fast' mode")
    parser.add_argument("--no_dehaze", action="store_true",
                         help="Skip automatic haze removal even on hazy-looking photos")
    parser.add_argument("--dehaze_strength", type=float, default=1.0,
                         help="0=no correction, 1=full Dark Channel Prior correction")
    parser.add_argument("--brightness_target", type=int, default=115,
                         help="Target mean brightness (0-255) after dehazing")
    args = parser.parse_args()

    img_path, modified_path, json_path, results = run(
        args.image, out_dir=args.out_dir, model_dir=args.model_dir,
        scuff_threshold=args.threshold, warn_ratio=args.warn_ratio,
        detect_conf=args.detect_conf, enhance=not args.no_enhance,
        sharpen_strength=args.sharpen, detector_mode=args.detector,
        max_boxes=args.max_boxes, region_quality=args.region_quality,
        auto_dehaze=not args.no_dehaze, dehaze_strength=args.dehaze_strength,
        brightness_target=args.brightness_target,
    )
    print(f"Saved annotated image -> {img_path}")
    print(f"Saved modified image  -> {modified_path}")
    print(f"Saved report          -> {json_path}")
    for r in results:
        print(f"  [{r['severity'].upper():8s}] {r['detector_label']} "
              f"(det.conf={r['detector_confidence']}) "
              f"scuff_score={r['scuff_score']} -> best_guess={r['best_guess']}")
