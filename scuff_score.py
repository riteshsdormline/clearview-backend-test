"""
"Scuff score" for an object crop: a heuristic, explainable damage/wear
indicator built from classical image-processing texture features (no
training data required). It combines four signals that are each cheap
to compute and individually interpretable:

1. edge_density       -- scratches/scuffs add lots of small, dense edges
                          on top of an object's normal silhouette edges.
2. block_contrast_var -- scuffed surfaces are patchy: some patches are
                          smooth, some are chewed-up/sharp. We measure the
                          *variance of local sharpness* across a grid of
                          blocks. A pristine, uniform surface has low
                          variance across blocks; a scuffed one is uneven.
3. texture_irregularity -- Local Binary Pattern histogram entropy. Random,
                          irregular micro-texture (scrapes, frays, chips)
                          pushes entropy up relative to a smooth material.
4. local_color_variability -- scuffs/wear often expose a different color
                          underneath (e.g. scraped paint, worn leather) or
                          leave dirt smudges, so local color variance
                          within small patches tends to increase.

These are combined into a single 0-1 "scuff_score". This is a proxy
heuristic, not a supervised model -- if you have labeled scuffed vs.
pristine images, swap `compute_scuff_score` for a small trained
classifier (e.g. a tiny CNN or even logistic regression on these same
four features) for much higher accuracy. The features are exposed
individually in the returned dict so you can inspect/retrain against them.
"""
import cv2
import numpy as np
from skimage.feature import local_binary_pattern


def _edge_density(gray):
    # Fixed Canny thresholds (the original 60/160) silently return zero
    # edges on low-contrast crops (hazy, underexposed, or just naturally
    # flat surfaces) -- that's why many hazy-photo detections came back
    # with edge_density exactly 0.0, understating how "edgy" the object
    # actually is once you account for the low dynamic range. Auto-scale
    # the thresholds to the crop's own contrast (median-based, a standard
    # adaptive-Canny heuristic) so this works across exposures.
    median = np.median(gray)
    sigma = 0.33
    lower = int(max(0, (1.0 - sigma) * median))
    upper = int(min(255, (1.0 + sigma) * median))
    if upper <= lower:
        upper = lower + 1
    edges = cv2.Canny(gray, lower, upper)
    return float(np.mean(edges > 0))


def _block_contrast_variance(gray, blocks=4):
    h, w = gray.shape
    bh, bw = max(1, h // blocks), max(1, w // blocks)
    sharpness_vals = []
    for i in range(blocks):
        for j in range(blocks):
            block = gray[i * bh:(i + 1) * bh, j * bw:(j + 1) * bw]
            if block.size == 0:
                continue
            lap = cv2.Laplacian(block, cv2.CV_64F)
            sharpness_vals.append(lap.var())
    if not sharpness_vals:
        return 0.0
    # normalize by mean to get a relative (scale-independent) variability
    mean_s = np.mean(sharpness_vals) + 1e-6
    return float(np.std(sharpness_vals) / mean_s)


def _texture_irregularity(gray, radius=2, n_points=16):
    lbp = local_binary_pattern(gray, n_points, radius, method="uniform")
    hist, _ = np.histogram(lbp, bins=n_points + 2, range=(0, n_points + 2), density=True)
    hist = hist[hist > 0]
    entropy = float(-np.sum(hist * np.log2(hist)))
    max_entropy = np.log2(n_points + 2)
    return entropy / max_entropy  # normalized 0-1


def _local_color_variability(bgr, blocks=4):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    h, w = sat.shape
    bh, bw = max(1, h // blocks), max(1, w // blocks)
    means = []
    for i in range(blocks):
        for j in range(blocks):
            block = sat[i * bh:(i + 1) * bh, j * bw:(j + 1) * bw]
            if block.size == 0:
                continue
            means.append(block.mean())
    if len(means) < 2:
        return 0.0
    return float(np.std(means) / (np.mean(means) + 1e-6))


def compute_scuff_score(crop_bgr, weights=(0.30, 0.30, 0.25, 0.15)):
    """
    crop_bgr: an OpenCV BGR image crop of a single detected object.
    weights: relative importance of (edge_density, block_contrast_var,
             texture_irregularity, local_color_variability).
    Returns dict with the combined 'scuff_score' (roughly 0-1, can exceed
    1 slightly for extreme cases) plus each raw component for inspection.
    """
    if crop_bgr is None or crop_bgr.size == 0:
        return {"scuff_score": 0.0}

    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (128, 128))
    bgr_resized = cv2.resize(crop_bgr, (128, 128))

    edge_density = _edge_density(gray)
    contrast_var = _block_contrast_variance(gray)
    texture_irreg = _texture_irregularity(gray)
    color_var = _local_color_variability(bgr_resized)

    # Empirically-chosen normalization caps so each feature contributes
    # roughly comparably before weighting (tune these on your own data).
    norm = [
        min(edge_density / 0.25, 1.0),
        min(contrast_var / 1.5, 1.0),
        texture_irreg,
        min(color_var / 0.5, 1.0),
    ]
    score = sum(w * v for w, v in zip(weights, norm))

    return {
        "scuff_score": round(float(score), 4),
        "edge_density": round(edge_density, 4),
        "block_contrast_variance": round(contrast_var, 4),
        "texture_irregularity": round(texture_irreg, 4),
        "local_color_variability": round(color_var, 4),
    }
