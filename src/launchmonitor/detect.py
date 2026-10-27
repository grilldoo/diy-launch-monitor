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


def _fit_circle(pts: np.ndarray) -> tuple[float, float, float]:
    """Algebraic (Kasa) least-squares circle: (u, v, r)."""
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones(len(x))])
    c, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    u, v = c[0] / 2, c[1] / 2
    return float(u), float(v), float(np.sqrt(c[2] + u * u + v * v))


def _fill_holes(bw: np.ndarray) -> np.ndarray:
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = np.zeros_like(bw)
    cv2.drawContours(out, contours, -1, 255, -1)
    return out


def detect_balls(img: np.ndarray, threshold: int = 60, min_radius_px: float = 12.0) -> list[BallBlob]:
    """Find lit ball images, even when another image (usually the club sticker after impact)
    touches or overlaps them.

    A distance transform finds the centres of the largest inscribed circles: only a ball is
    that thick, since a sticker seen edge-on is a narrow strip. Each circle is then refined
    by fitting the boundary points near it, with outliers (where something else is attached)
    rejected.
    """
    _, bw = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    bw = _fill_holes(bw)  # marking dots would otherwise punch holes in the distance transform
    dt = cv2.distanceTransform(bw, cv2.DIST_L2, 5)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    edge = np.vstack([c.reshape(-1, 2) for c in contours]).astype(float) if contours else np.zeros((0, 2))
    work = dt.copy()
    found: list[tuple[float, float, float]] = []
    largest = None
    while True:
        _, peak, _, (pu, pv) = cv2.minMaxLoc(work)
        if peak < min_radius_px or (largest is not None and peak < 0.6 * largest):
            break
        largest = largest or peak
        u, v, r = float(pu), float(pv), float(peak)
        near = edge[:0]
        # Refine on nearby boundary points with a shrinking tolerance, so the edges of an
        # attached sticker drop out and only the ball's own outline is fitted.
        for tol in (0.15 * r, 0.06 * r, 3.0, 2.0, 1.5):
            d = np.hypot(edge[:, 0] - u, edge[:, 1] - v)
            cand = edge[np.abs(d - r) < max(tol, 1.5)]
            if len(cand) < 20:
                break
            near = cand
            u, v, r = _fit_circle(near)
        coverage = len(near) / (2 * np.pi * r) if len(near) >= 20 else 0.0
        cv2.circle(work, (int(pu), int(pv)), int(peak * 1.15) + 2, 0, -1)
        # A third of the outline is plenty for a circle fit; after impact the club's sticker
        # images can cover the lower half of the resting ball and the first ball image.
        if coverage > 0.35:
            found.append((u, v, r))
    blobs = []
    for u, v, r in found:
        mask = np.zeros_like(img)
        cv2.circle(mask, (int(round(u)), int(round(v))), max(int(0.8 * r), 1), 255, -1)
        blobs.append(BallBlob(u, v, r, float(cv2.mean(img, mask)[0])))
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


@dataclass
class StickerBlob:
    u: float  # region centroid
    v: float
    dots: list[np.ndarray]


def detect_stickers(img: np.ndarray, balls: list[BallBlob], threshold: int = 60, min_area_px: int = 250) -> list[StickerBlob]:
    """Bright regions that aren't balls and contain 4-5 dark dots: club-face sticker images.
    A region holding several touching sticker images is split by clustering its dots."""
    _, bw = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)
    for b in balls:  # remove the balls (and a rim) so overlapping stickers separate from them
        cv2.circle(bw, (int(round(b.u)), int(round(b.v))), int(b.radius * 1.06) + 3, 0, -1)
    bw = _fill_holes(cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(bw, connectivity=8)
    out = []
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < min_area_px:
            continue
        x, y, w, h = stats[i, :4]
        x0, y0, x1, y1 = max(x - 2, 0), max(y - 2, 0), min(x + w + 2, img.shape[1]), min(y + h + 2, img.shape[0])
        region = (labels[y0:y1, x0:x1] == i).astype(np.uint8)
        inner = cv2.erode(region, np.ones((3, 3), np.uint8))  # dots touching the outline are unreliable
        crop = img[y0:y1, x0:x1].astype(np.float32)
        lit = np.where(region > 0, crop, 0)
        k = max(7, int(0.35 * min(w, h)) | 1)
        bg = cv2.morphologyEx(lit, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        ratio = lit / np.maximum(bg, 1.0)
        dark = ((ratio < 0.55) & (inner > 0) & (bg > threshold)).astype(np.uint8)
        m, dl, dstats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
        ys, xs = np.mgrid[y0:y1, x0:x1]
        weight = np.clip(1.0 - ratio, 0, None)
        dots = []
        for j in range(1, m):
            if dstats[j, cv2.CC_STAT_AREA] < 4:
                continue
            mm = dl == j
            wj = weight[mm]
            dots.append(np.array([(xs[mm] * wj).sum() / wj.sum(), (ys[mm] * wj).sum() / wj.sum()]))
        if 4 <= len(dots) <= 6:
            out.append(StickerBlob(float(cents[i][0]), float(cents[i][1]), dots))
        elif len(dots) > 6:
            # Two or more sticker images touching (slow swings bring the flashes closer
            # together): split the dots into one cluster per sticker. Each cluster still has
            # to pass the layout fit in label_sticker, so a bad split is rejected, not mislabelled.
            k = int(round(len(dots) / 5))
            pts = np.array(dots, np.float32)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1)
            _, lab, centers = cv2.kmeans(pts, k, None, crit, 10, cv2.KMEANS_PP_CENTERS)
            for c in range(k):
                grp = [dots[j] for j in np.flatnonzero(lab.ravel() == c)]
                if 4 <= len(grp) <= 5:
                    out.append(StickerBlob(float(centers[c][0]), float(centers[c][1]), grp))
    return out


def label_sticker(dots: list[np.ndarray], model_uv: np.ndarray, max_rms_px: float = 2.0,
                  min_margin: float = 2.0) -> dict[int, np.ndarray] | None:
    """Which detected dot is which marker id, by fitting the known layout.

    Every assignment of detected dots to model dots (120 for 5 dots, or for 4 dots with one
    missing) is fitted with an affine map: the sticker is small and far away, so perspective
    adds under ~1 px. Assignments that would need a mirror image are skipped: the cameras
    always see the sticker from the front, which makes the map's determinant positive (checked
    over every simulated rig and shot). The best fit wins only if it fits well *and* clearly
    beats the runner-up; an ambiguous sticker is dropped, since a wrong label gives a wrong
    face angle while a missing one just costs that flash.
    """
    import itertools

    P = np.asarray(dots, float)
    k = len(P)
    if k not in (4, 5) or k > len(model_uv):
        return None
    M = np.asarray(model_uv, float) * 1000  # mm, for conditioning
    fits = []
    for ids in itertools.permutations(range(len(M)), k):
        A = np.column_stack([M[list(ids)], np.ones(k)])
        coef, *_ = np.linalg.lstsq(A, P, rcond=None)
        if np.linalg.det(coef[:2, :2]) <= 0:  # mirror image: impossible from the front
            continue
        rms = float(np.sqrt(np.mean(np.sum((A @ coef - P) ** 2, axis=1))))
        fits.append((rms, ids))
    if not fits:
        return None
    fits.sort(key=lambda f: f[0])
    best = fits[0]
    if best[0] > max_rms_px or (len(fits) > 1 and fits[1][0] < min_margin * max(best[0], 0.3)):
        return None
    return {int(i): P[j] for j, i in enumerate(best[1])}


def find_resting_ball(img: np.ndarray, balls: list[BallBlob], saturated: int = 240) -> BallBlob | None:
    """The resting ball is lit by every flash, so its image is saturated all over. The
    biggest inscribed circle in the saturated pixels finds it, even if the ball detector
    missed it. (Where a sticker image overlaps a ball it can saturate too, but only in thin slivers.)"""
    _, sat = cv2.threshold(img, saturated, 255, cv2.THRESH_BINARY)
    sat = _fill_holes(sat)
    dt = cv2.distanceTransform(sat, cv2.DIST_L2, 5)
    _, peak, _, (pu, pv) = cv2.minMaxLoc(dt)
    if peak < 10:
        return None
    for b in balls:
        if np.hypot(b.u - pu, b.v - pv) < 0.5 * b.radius:
            return b
    return BallBlob(float(pu), float(pv), float(peak), 255.0)


def assign_flash_steps(dists: list[float], n_flashes: int) -> list[int] | None:
    """Flash index of each moving-ball image from its distance to the resting ball.

    Ball flashes are evenly spaced in time, so the images are roughly evenly spaced (to within
    perspective, ~+-20%). A missing image (hidden, merged, off the frame) shows up as a double
    gap instead of silently shifting every later image to the wrong flash. Returns None if the
    spacing is inconsistent.
    """
    if not dists:
        return []
    gaps = np.diff([0.0] + list(dists))
    step = float(np.min(gaps))
    if step <= 0:
        return None
    idx, k = [], -1
    for gap in gaps:
        n = gap / step
        if abs(n - round(n)) > 0.35 or round(n) < 1:
            return None
        k += int(round(n))
        idx.append(k)
        step = 0.5 * step + 0.5 * gap / round(n)  # follow the slow change in spacing with perspective
    return idx if idx[-1] < n_flashes else None


def detect_shot(frames: dict, flash_kinds: list[int], flash_times_s: list[float], threshold: int = 60):
    """Multi-exposure frames (camera name -> image) -> ShotObservation.

    Balls: the resting ball is the brightest blob (every flash lit it). Moving-ball images
    are ordered by distance from it, which matches flash order because the ball only moves
    away.
    Club: sticker images *behind* the resting ball (opposite side from the ball flight) are
    the club before impact; the ones nearest the ball are the latest club flashes. Sticker
    images ahead of it are the club after impact, lit by the ball flashes, and are ignored.
    Ball dots come out unlabeled (dots.label_dots); sticker dots are labeled here.
    """
    from .markers import FACE_MARKERS_UV  # noqa: PLC0415

    ball_flashes = [i for i, k in enumerate(flash_kinds) if k == FLASH_BALL]
    club_flashes = [i for i, k in enumerate(flash_kinds) if k != FLASH_BALL]
    obs = ShotObservation(list(flash_times_s), list(flash_kinds))
    for name, img in frames.items():
        blobs = detect_balls(img, threshold)
        rest = find_resting_ball(img, blobs)
        if rest is None:
            continue
        if rest not in blobs:
            blobs.append(rest)
        moving = sorted((b for b in blobs if b is not rest), key=lambda b: np.hypot(b.u - rest.u, b.v - rest.v))
        steps = assign_flash_steps([float(np.hypot(b.u - rest.u, b.v - rest.v)) for b in moving], len(ball_flashes))
        if steps is None:  # can't tell which image is which flash: better no data than wrong data
            continue
        for k, b in zip(steps, moving):
            f = ball_flashes[k]
            obs.detections.append(Detection(name, f, "ball", 0, np.array([b.u, b.v])))
            for uv in detect_dots(img, b):
                obs.detections.append(Detection(name, f, "dot", -1, uv))
        if not club_flashes or not moving:
            continue
        fwd = np.array([moving[0].u - rest.u, moving[0].v - rest.v])
        fwd /= np.linalg.norm(fwd)
        behind = []
        for st in detect_stickers(img, blobs, threshold):
            along = (st.u - rest.u) * fwd[0] + (st.v - rest.v) * fwd[1]
            if along < -0.5 * rest.radius:
                behind.append((along, st))
        behind.sort(key=lambda x: x[0])  # earliest (furthest back) first
        for f, (_, st) in zip(club_flashes[::-1], behind[::-1]):  # latest flash <-> nearest the ball
            labels = label_sticker(st.dots, FACE_MARKERS_UV) if len(st.dots) <= 5 else None
            for mid, uv in (labels or {}).items():
                obs.detections.append(Detection(name, f, "marker", mid, uv))
    return obs
