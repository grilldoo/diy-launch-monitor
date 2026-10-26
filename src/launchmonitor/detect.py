"""Image detection on multi-exposure IR frames."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .models import Detection, ShotObservation
from .schedule import FLASH_BALL


@dataclass
class BallBlob:
    u: float
    v: float
    radius: float
    brightness: float  # mean pixel value; the resting ball (lit by every flash) is brightest


def detect_balls(img: np.ndarray, threshold: int = 60, min_radius_px: float = 12.0) -> list[BallBlob]:
    """Find lit ball images. Uses the outer contour, so dark marking dots don't matter
    except where they notch the edge; minEnclosingCircle rides over those notches."""
    _, bw = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    blobs = []
    for c in contours:
        if cv2.contourArea(c) < np.pi * min_radius_px**2:
            continue
        (u, v), r = cv2.minEnclosingCircle(c)
        if cv2.contourArea(c) / (np.pi * r * r) < 0.6:  # not round: overlapping images or club
            continue
        mask = np.zeros_like(img)
        cv2.drawContours(mask, [c], -1, 255, -1)
        blobs.append(BallBlob(float(u), float(v), float(r), float(cv2.mean(img, mask)[0])))
    return blobs


def detect_dots(img: np.ndarray, blob: BallBlob, limb_frac: float = 0.9, dark_ratio: float = 0.55) -> list[np.ndarray]:
    """Dark marking dots inside one ball image. Returns sub-pixel centroids.

    Background shading is estimated with a morphological closing (which fills the dots),
    so the threshold is relative to the local ball brightness. Dots beyond `limb_frac` of
    the radius are skipped: too foreshortened to centre reliably. That ring corresponds
    to the 0.35 view-cosine cut-off the simulator uses. Dots cut by the ball's edge are
    dropped rather than kept as biased half-dots.
    """
    r = blob.radius
    x0, y0 = int(max(blob.u - r - 2, 0)), int(max(blob.v - r - 2, 0))
    x1, y1 = int(min(blob.u + r + 3, img.shape[1])), int(min(blob.v + r + 3, img.shape[0]))
    crop = img[y0:y1, x0:x1].astype(np.float32)
    k = max(3, int(0.3 * r) | 1)
    bg = cv2.morphologyEx(crop, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    ratio = crop / np.maximum(bg, 1.0)
    ys, xs = np.mgrid[y0:y1, x0:x1]
    rad = np.hypot(xs - blob.u, ys - blob.v)
    dark = ((ratio < dark_ratio) & (rad < 0.97 * r)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    out = []
    weight = np.clip(1.0 - ratio, 0, None)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 4:
            continue
        m = labels == i
        if rad[m].max() > 0.94 * r:  # touches the limb
            continue
        w = weight[m]
        c = np.array([(xs[m] * w).sum() / w.sum(), (ys[m] * w).sum() / w.sum()])
        if np.hypot(c[0] - blob.u, c[1] - blob.v) < limb_frac * r:
            out.append(c)
    return out


def detect_shot(frames: dict, flash_kinds: list[int], flash_times_s: list[float], threshold: int = 60):
    """Multi-exposure frames (camera name -> image) -> ShotObservation with unlabeled dots.

    Flash assignment: the resting ball is the brightest blob (every club flash lit it).
    Moving-ball images are ordered by distance from it, which matches flash order
    because the ball only moves away.
    """
    ball_flashes = [i for i, k in enumerate(flash_kinds) if k == FLASH_BALL]
    obs = ShotObservation(list(flash_times_s), list(flash_kinds))
    for name, img in frames.items():
        blobs = detect_balls(img, threshold)
        if len(blobs) < 2:
            continue
        rest = max(blobs, key=lambda b: b.brightness)
        moving = sorted((b for b in blobs if b is not rest), key=lambda b: np.hypot(b.u - rest.u, b.v - rest.v))
        for f, b in zip(ball_flashes, moving):
            obs.detections.append(Detection(name, f, "ball", 0, np.array([b.u, b.v])))
            for uv in detect_dots(img, b):
                obs.detections.append(Detection(name, f, "dot", -1, uv))
    return obs
