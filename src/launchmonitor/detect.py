"""Image detection on multi-exposure IR frames."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


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
