"""Ball-dot matching: unlabeled dot detections -> pattern ids.

Real detection finds dark dots on each ball image but not *which* dot each one is.
Per flash:
  1. back-project every dot onto the ball sphere (centre triangulated from the ball
     circles, known radius). This works from a single camera, so dots seen by only
     one camera still count.
  2. merge points from different cameras that land on the same spot
  3. find the rotation of the known marking pattern (data/ball_pattern.json) that
     best explains the points: coarse search over a fixed rotation grid, then ICP
     on the best few candidates. Scoring also penalises pattern dots that *should*
     be visible but weren't detected, which is what makes the fit unambiguous.
  4. give every detection the id of the nearest rotated pattern dot
The labeled observation then goes to solver.solve() unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import geometry as g
from .camera import Camera, triangulate
from .models import BALL_RADIUS_M, Detection, ShotObservation
from .rig import Rig
from .schedule import FLASH_BALL

PATTERN_FILE = Path(__file__).with_name("data") / "ball_pattern.json"
MATCH_CAP_RAD = np.radians(12.0)  # a detection further than this from every pattern dot is unexplained
LABEL_MAX_RAD = np.radians(8.0)  # max distance to accept an id after the fit
MERGE_TOL_M = 0.0015
# A pattern dot facing the cameras this squarely should have been detected. Stricter than
# the detector's own limb cut-off, so this never penalises dots the detector would skip.
PREDICT_VISIBLE_COS = 0.6
GRID_SIZE = 12000
N_CANDIDATES = 8


@lru_cache(maxsize=1)
def load_pattern() -> np.ndarray:
    data = json.loads(PATTERN_FILE.read_text())
    p = np.asarray(data["dots"], float)
    return p / np.linalg.norm(p, axis=1, keepdims=True)


@lru_cache(maxsize=1)
def _rotation_grid() -> np.ndarray:
    """Uniform random rotations (fixed seed). ~10 deg mean spacing at 12k samples."""
    q = np.random.default_rng(12345).normal(size=(GRID_SIZE, 4))
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T
    return np.stack(
        [
            np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
            np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
            np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1),
        ],
        axis=1,
    )


def sphere_points(cam: Camera, uvs: np.ndarray, center: np.ndarray, radius: float = BALL_RADIUS_M) -> np.ndarray:
    """Nearest ray-sphere intersection for each pixel; NaN rows where the ray misses."""
    uvs = np.atleast_2d(uvs)
    rays_cam = np.column_stack([uvs, np.ones(len(uvs))]) @ np.linalg.inv(cam.K).T
    d = rays_cam @ cam.R  # camera -> world (R is world -> camera)
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    o = cam.center
    oc = o - center
    b = d @ oc
    disc = b * b - (oc @ oc - radius * radius)
    out = np.full((len(uvs), 3), np.nan)
    ok = disc >= 0
    s = -b[ok] - np.sqrt(disc[ok])
    out[ok] = o + s[:, None] * d[ok]
    return out


def merge_points(points: np.ndarray, tol: float = MERGE_TOL_M) -> tuple[np.ndarray, np.ndarray]:
    """Greedy clustering. Returns (cluster centres, cluster index per input point)."""
    labels = -np.ones(len(points), int)
    centers: list[np.ndarray] = []
    for i, p in enumerate(points):
        if centers:
            dist = np.linalg.norm(np.asarray(centers) - p, axis=1)
            j = int(np.argmin(dist))
            if dist[j] < tol:
                labels[i] = j
                continue
        labels[i] = len(centers)
        centers.append(p)
    C = np.array([points[labels == k].mean(axis=0) for k in range(len(centers))]) if centers else np.zeros((0, 3))
    return C, labels


@dataclass
class OrientationFit:
    R: np.ndarray  # world_dir = R @ pattern_dir
    cost: float
    rms_deg: float
    n_matched: int
    n_missing: int  # pattern dots predicted visible but not detected


def _cost(obs: np.ndarray, rotated: np.ndarray, view: np.ndarray) -> np.ndarray:
    """Vectorised cost for rotated patterns (..., n, 3) against observed unit vectors (k, 3)."""
    cos = np.einsum("kc,...nc->...kn", obs, rotated)
    ang = np.arccos(np.clip(cos.max(axis=-1), -1, 1))
    unexplained = np.minimum(ang, MATCH_CAP_RAD) ** 2
    vis = (rotated @ view) > PREDICT_VISIBLE_COS
    has_obs = cos.max(axis=-2) > np.cos(MATCH_CAP_RAD)
    missing = (vis & ~has_obs).sum(axis=-1)
    return unexplained.sum(axis=-1) + missing * MATCH_CAP_RAD**2


def fit_orientation(obs_dirs: np.ndarray, view_dir: np.ndarray, pattern: np.ndarray | None = None) -> OrientationFit | None:
    """Rotation of `pattern` that best matches observed dot directions (unit vectors, ball frame)."""
    pattern = load_pattern() if pattern is None else pattern
    if len(obs_dirs) < 3:
        return None
    grid = _rotation_grid()
    costs = _cost(obs_dirs, np.einsum("gij,nj->gni", grid, pattern), view_dir)
    best = None
    for gi in np.argsort(costs)[:N_CANDIDATES]:
        R = grid[gi]
        for _ in range(15):  # ICP
            rot = pattern @ R.T
            cos = obs_dirs @ rot.T
            nn = cos.argmax(axis=1)
            keep = np.arccos(np.clip(cos[np.arange(len(nn)), nn], -1, 1)) < MATCH_CAP_RAD
            if keep.sum() < 3:
                break
            R_new = g.kabsch(pattern[nn[keep]], obs_dirs[keep])
            if np.allclose(R_new, R, atol=1e-9):
                break
            R = R_new
        c = float(_cost(obs_dirs, pattern @ R.T, view_dir))
        if best is None or c < best.cost:
            rot = pattern @ R.T
            cos = obs_dirs @ rot.T
            ang = np.arccos(np.clip(cos.max(axis=1), -1, 1))
            matched = ang < MATCH_CAP_RAD
            vis = (rot @ view_dir) > PREDICT_VISIBLE_COS
            missing = int((vis & ~((cos > np.cos(MATCH_CAP_RAD)).any(axis=0))).sum())
            rms = float(np.degrees(np.sqrt(np.mean(ang[matched] ** 2)))) if matched.any() else 90.0
            best = OrientationFit(R, c, rms, int(matched.sum()), missing)
    return best


def label_dots(obs: ShotObservation, rig: Rig, pattern: np.ndarray | None = None) -> tuple[ShotObservation, dict[int, OrientationFit]]:
    """Assign pattern ids to unlabeled ("dot", id < 0) detections. Returns (new obs, fit per flash)."""
    pattern = load_pattern() if pattern is None else pattern
    cams = {c.name: c for c in rig.ball_cams}
    out: list[Detection] = [d for d in obs.detections if not (d.kind == "dot" and d.id < 0)]
    fits: dict[int, OrientationFit] = {}
    for f, kind in enumerate(obs.flash_kinds):
        if kind != FLASH_BALL:
            continue
        balls = [d for d in obs.detections if d.kind == "ball" and d.flash == f and d.camera in cams]
        dots = [d for d in obs.detections if d.kind == "dot" and d.id < 0 and d.flash == f and d.camera in cams]
        if len(balls) < 2 or len(dots) < 3:
            continue
        center = triangulate([cams[d.camera] for d in balls], [d.uv for d in balls])
        pts = np.vstack([sphere_points(cams[d.camera], d.uv, center) for d in dots])
        ok = ~np.isnan(pts[:, 0])
        if ok.sum() < 3:
            continue
        merged, labels = merge_points(pts[ok])
        dirs = (merged - center) / np.linalg.norm(merged - center, axis=1, keepdims=True)
        view = np.mean([cams[d.camera].center - center for d in balls], axis=0)
        view /= np.linalg.norm(view)
        fit = fit_orientation(dirs, view, pattern)
        if fit is None:
            continue
        fits[f] = fit
        rot = pattern @ fit.R.T
        ok_idx = np.flatnonzero(ok)
        for j, d in enumerate(dots):
            if not ok[j]:
                continue
            u = dirs[labels[np.searchsorted(ok_idx, j)]]
            cos = rot @ u
            k = int(cos.argmax())
            if np.arccos(min(cos[k], 1.0)) < LABEL_MAX_RAD:
                out.append(replace(d, id=k))
    return ShotObservation(obs.flash_times_s, obs.flash_kinds, out), fits
