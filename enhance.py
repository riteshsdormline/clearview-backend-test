"""
Image clarity enhancement -- separate from scuff scoring/detection.

Runs on the *whole* output image (not just scuffed crops) so the final
photo genuinely looks better, not just annotated: mild denoise, local
contrast boost (CLAHE on the L channel in LAB space, avoids washing out
color), and an unsharp-mask sharpen. All three are intentionally gentle by
default -- this is a clarity pass, not an Instagram filter.
"""
import cv2
import numpy as np


def enhance_image(image_bgr, denoise_strength=3, clahe_clip=2.0, sharpen_strength=0.5):
    """
    image_bgr: full OpenCV BGR image (uint8).
    denoise_strength: 0 disables denoising. Higher = smoother but softer.
    clahe_clip: CLAHE clip limit; higher = more local contrast (can amplify
        noise if denoise_strength is 0).
    sharpen_strength: 0 disables sharpening. ~0.3-0.8 is a natural range;
        above ~1.2 starts looking artificially crunchy.
    """
    out = image_bgr

    if denoise_strength > 0:
        # Use a faster, lighter denoising for general clarity if the image
        # is large, to avoid server timeouts. fastNlMeans is very slow.
        if max(out.shape[:2]) > 800:
            out = cv2.medianBlur(out, 3)
        else:
            out = cv2.fastNlMeansDenoisingColored(
                out, None, denoise_strength, denoise_strength, 7, 21
            )

    if clahe_clip > 0:
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
        l = clahe.apply(l)
        out = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

    if sharpen_strength > 0:
        blurred = cv2.GaussianBlur(out, (0, 0), sigmaX=3)
        out = cv2.addWeighted(
            out, 1 + sharpen_strength, blurred, -sharpen_strength, 0
        )

    return out


def enhance_crop(crop_bgr, **kwargs):
    """Same enhancement, scoped to just one crop -- useful if you want the
    scuffed-object regions extra crisp without paying the cost of running
    denoise/CLAHE over the full-resolution image."""
    if crop_bgr is None or crop_bgr.size == 0:
        return crop_bgr
    return enhance_image(crop_bgr, **kwargs)
