"""
Single-image haze removal via the Dark Channel Prior (He, Sun, Tang 2009).

Why this instead of just histogram equalization / CLAHE: haze physically
adds a veil of atmospheric light that's roughly uniform across the scene
(cv2.equalizeHist / CLAHE redistribute contrast but can't remove that veil,
so hazy photos stay washed-out looking after them). Dark Channel Prior
actually estimates *how much haze* is over each pixel and inverts the
physical haze formation model (I = J*t + A*(1-t)) to recover the clear
scene radiance J. This is the standard classical (pre-deep-learning)
dehazing algorithm and needs no trained weights, so it's free to bundle.

Pipeline:
  1. dark channel of the hazy image -> rough haze density map
  2. atmospheric light A estimated from the haziest 0.1% of pixels
  3. transmission map t estimated from the dark channel, refined with a
     guided filter (edge-aware smoothing using the image itself as guide,
     avoids blocky artifacts at object boundaries)
  4. invert the haze model to recover the clear image
"""
import cv2
import numpy as np


def _dark_channel(img_float, patch_size=15):
    """img_float: HxWx3, values in [0,1]."""
    min_channel = np.min(img_float, axis=2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (patch_size, patch_size))
    return cv2.erode(min_channel, kernel)


def _atmospheric_light(img_float, dark_channel, top_fraction=0.001):
    h, w = dark_channel.shape
    num_pixels = h * w
    num_top = max(int(num_pixels * top_fraction), 1)

    dark_flat = dark_channel.reshape(num_pixels)
    img_flat = img_float.reshape(num_pixels, 3)

    top_indices = np.argsort(dark_flat)[-num_top:]
    # Brightest of the haziest pixels -- standard heuristic for estimating
    # the atmospheric light color/intensity.
    brightest_idx = top_indices[np.argmax(img_flat[top_indices].sum(axis=1))]
    return img_flat[brightest_idx]


def _transmission_estimate(img_float, atmosphere, patch_size=15, omega=0.95):
    normalized = img_float / np.maximum(atmosphere, 1e-6)
    dark = _dark_channel(normalized, patch_size)
    return 1.0 - omega * dark


def _guided_filter(guide_gray, src, radius=40, eps=1e-3):
    """Edge-aware smoothing of `src` guided by `guide_gray`, both float in
    [0,1]. Standard fast guided filter (He et al. 2010), box-filter based."""
    mean_guide = cv2.boxFilter(guide_gray, cv2.CV_64F, (radius, radius))
    mean_src = cv2.boxFilter(src, cv2.CV_64F, (radius, radius))
    mean_guide_src = cv2.boxFilter(guide_gray * src, cv2.CV_64F, (radius, radius))
    cov_guide_src = mean_guide_src - mean_guide * mean_src

    mean_guide_sq = cv2.boxFilter(guide_gray * guide_gray, cv2.CV_64F, (radius, radius))
    var_guide = mean_guide_sq - mean_guide * mean_guide

    a = cov_guide_src / (var_guide + eps)
    b = mean_src - a * mean_guide

    mean_a = cv2.boxFilter(a, cv2.CV_64F, (radius, radius))
    mean_b = cv2.boxFilter(b, cv2.CV_64F, (radius, radius))

    return mean_a * guide_gray + mean_b


def dehaze(image_bgr, patch_size=15, omega=0.95, t_min=0.15,
           guided_radius=40, guided_eps=1e-3, strength=1.0):
    """
    image_bgr: uint8 BGR image.
    strength: 0 = no change, 1 = full correction. Useful for avoiding
        over-correction on only-mildly-hazy photos (try 0.6-0.8 there).
    Returns: uint8 BGR dehazed image, same size.
    """
    img_float = image_bgr.astype(np.float64) / 255.0

    dark = _dark_channel(img_float, patch_size)
    atmosphere = _atmospheric_light(img_float, dark)
    transmission = _transmission_estimate(img_float, atmosphere, patch_size, omega)

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
    transmission_refined = _guided_filter(gray, transmission, guided_radius, guided_eps)
    transmission_refined = np.clip(transmission_refined, t_min, 1.0)

    result = np.empty_like(img_float)
    for c in range(3):
        result[:, :, c] = (img_float[:, :, c] - atmosphere[c]) / transmission_refined + atmosphere[c]
    result = np.clip(result, 0.0, 1.0)

    if strength < 1.0:
        result = strength * result + (1 - strength) * img_float

    return (result * 255).astype(np.uint8)


def estimate_haze_level(image_bgr, patch_size=15):
    """
    Rough 0-1 haze severity estimate (mean dark channel value -- clear
    outdoor images have dark channels near 0; hazy ones are much higher).
    Useful for deciding whether to bother dehazing at all, or how strongly.
    """
    img_float = image_bgr.astype(np.float64) / 255.0
    dark = _dark_channel(img_float, patch_size)
    return float(np.mean(dark))


def auto_brightness(image_bgr, target_mean=140):
    """
    Dark Channel Prior dehazing systematically under-brightens results (it
    removes the atmospheric-light veil without independently correcting
    exposure). This is a simple gamma correction to bring the result back
    to a natural brightness level without re-introducing haze.
    """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    current_mean = max(float(np.mean(gray)), 1.0)
    gamma = np.log(target_mean / 255.0) / np.log(current_mean / 255.0)
    gamma = np.clip(gamma, 0.3, 3.0)

    lut = np.array([((i / 255.0) ** gamma) * 255 for i in range(256)]).astype(np.uint8)
    return cv2.LUT(image_bgr, lut)
