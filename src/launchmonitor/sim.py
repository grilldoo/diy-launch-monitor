"""Synthetic shot generator.

Turns known launch conditions into what the cameras would report, so the solver
can be developed and regression-tested without hardware. Two levels:
  * simulate()  -> ShotObservation of ideal 2D detections (+ pixel noise), with
                   dot ids (labeled=True) or without, as real detection gives them
  * render()    -> multi-exposure IR frames, for testing the detectors themselves
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import geometry as g
from .camera import Camera
from .dots import load_pattern
from .models import BALL_RADIUS_M, Detection, ShotObservation, ShotTruth
from .rig import Rig
from .schedule import FLASH_BALL, FLASH_CLUB, TimingConfig, compute_schedule


def ball_dot_pattern() -> np.ndarray:
    """Unit vectors of the ball marking pattern (data/ball_pattern.json; printed with the jig)."""
    return load_pattern()


# Club-face sticker dots in face coordinates (u toward toe, v up the face), metres.
# Asymmetric so the layout has a unique orientation.
FACE_MARKERS_UV = np.array([[0.006, 0.007], [0.028, 0.007], [0.006, -0.006], [0.024, -0.008]])


def face_axes(face_deg: float, loft_deg: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(normal, toe, up) unit vectors of the club face. Toe points toward +z for a right-hander."""
    n = g.direction(face_deg, loft_deg)
    toe = g.Z_RIGHT - (g.Z_RIGHT @ n) * n
    toe /= np.linalg.norm(toe)
    up = np.cross(toe, n)
    return n, toe, up


@dataclass
class SimState:
    """Ground-truth geometry at each flash (for debugging and rendering)."""

    flash_times_s: list[float]
    flash_kinds: list[int]
    ball_centers: list[np.ndarray]
    ball_dots: list[np.ndarray]  # (n,3) world positions
    club_markers: list[np.ndarray | None]


def shot_state(
    truth: ShotTruth,
    timing: TimingConfig | None = None,
    impact_error_s: float = 0.0,
    dots: np.ndarray | None = None,
    initial_orientation: np.ndarray | None = None,
) -> SimState:
    timing = timing or TimingConfig()
    dots = ball_dot_pattern() if dots is None else dots
    R0 = np.eye(3) if initial_orientation is None else initial_orientation

    # Gate crossings for this club speed (gate 1 at t=0).
    gap_us = (timing.gate1_m - timing.gate2_m) / truth.club_speed_mps * 1e6
    sched = compute_schedule(timing, 0, int(round(gap_us)))
    if not sched.ok:
        raise ValueError(f"schedule failed: {sched.error}")
    times = [(t - sched.t_impact_us) * 1e-6 for t, _ in sched.flashes]
    kinds = [k for _, k in sched.flashes]

    v_ball = truth.ball_speed_mps * g.direction(truth.hla_deg, truth.vla_deg)
    right, up = g.spin_frame(g.direction(truth.hla_deg, truth.vla_deg))
    omega = (truth.backspin_rpm * right - truth.sidespin_rpm * up) * (2 * np.pi / 60)

    n, toe, fup = face_axes(truth.face_deg, truth.loft_deg)
    v_club = truth.club_speed_mps * g.direction(truth.path_deg, truth.attack_deg)
    face_center_at_impact = -BALL_RADIUS_M * n

    centers, dot_pos, markers = [], [], []
    for t in times:
        tt = t - impact_error_s  # time since the *actual* impact
        moving = tt > 0
        c = v_ball * tt if moving else np.zeros(3)
        Rt = g.rotvec_to_matrix(omega * tt) @ R0 if moving else R0
        centers.append(c)
        dot_pos.append(c + BALL_RADIUS_M * (dots @ Rt.T))
        if tt < 0:
            fc = face_center_at_impact + v_club * tt
            markers.append(fc + np.outer(FACE_MARKERS_UV[:, 0], toe) + np.outer(FACE_MARKERS_UV[:, 1], fup))
        else:
            markers.append(None)
    return SimState(times, kinds, centers, dot_pos, markers)


def _ray_hits_ball(origin: np.ndarray, target: np.ndarray, center: np.ndarray) -> bool:
    d = target - origin
    L = np.linalg.norm(d)
    d /= L
    oc = center - origin
    s = oc @ d
    if s <= 0 or s >= L - 1e-4:
        return False
    return np.linalg.norm(oc - s * d) < BALL_RADIUS_M


def observe(
    state: SimState, rig: Rig, rng: np.random.Generator, pixel_noise: float = 0.15, labeled: bool = True
) -> ShotObservation:
    obs = ShotObservation(state.flash_times_s, state.flash_kinds)

    def add(cam: Camera, i: int, kind: str, ids, pts):
        uv, depth = cam.project(pts)
        ok = cam.in_image(uv, depth)
        for j, idx in enumerate(ids):
            if ok[j]:
                did = int(idx) if labeled or kind != "dot" else -1
                obs.detections.append(Detection(cam.name, i, kind, did, uv[j] + rng.normal(0, pixel_noise, 2)))

    for i, kind in enumerate(state.flash_kinds):
        c = state.ball_centers[i]
        if kind == FLASH_BALL:
            for cam in rig.ball_cams:
                add(cam, i, "ball", [0], c[None])
                cc = cam.center
                normals = (state.ball_dots[i] - c) / BALL_RADIUS_M
                to_cam = cc - state.ball_dots[i]
                to_cam /= np.linalg.norm(to_cam, axis=1, keepdims=True)
                # Dots too close to the limb are unreliable; require >~20 deg above it.
                vis = np.where(np.einsum("ij,ij->i", normals, to_cam) > 0.35)[0]
                add(cam, i, "dot", vis, state.ball_dots[i][vis])
        elif kind == FLASH_CLUB and state.club_markers[i] is not None:
            m = state.club_markers[i]
            for cam in rig.club_cams:
                n_face = np.cross(m[1] - m[0], m[2] - m[0])
                n_face /= np.linalg.norm(n_face)
                vis = []
                for j, p in enumerate(m):
                    to_cam = cam.center - p
                    to_cam /= np.linalg.norm(to_cam)
                    if abs(n_face @ to_cam) > 0.17 and not _ray_hits_ball(cam.center, p, c):
                        vis.append(j)
                add(cam, i, "marker", vis, m[vis])
    return obs


def simulate(
    truth: ShotTruth,
    rig: Rig,
    seed: int = 0,
    pixel_noise: float = 0.15,
    impact_error_s: float = 0.0,
    timing: TimingConfig | None = None,
    labeled: bool = True,
) -> tuple[ShotObservation, SimState]:
    rng = np.random.default_rng(seed)
    q = rng.normal(size=3)
    R0 = g.rotvec_to_matrix(q / np.linalg.norm(q) * rng.uniform(0, np.pi))
    state = shot_state(truth, timing, impact_error_s, initial_orientation=R0)
    return observe(state, rig, rng, pixel_noise, labeled), state


def render(
    state: SimState,
    cam: Camera,
    rng: np.random.Generator | None = None,
    noise: float = 3.0,
    dot_diameter_m: float = 0.0035,
    supersample: int = 2,
) -> np.ndarray:
    """Render one multi-exposure 8-bit frame: every flash adds a lit ball with dark dots.

    Rays are traced against the sphere, so dots foreshorten correctly toward the limb.
    The strobe sits next to the cameras, so shading follows the view angle. The resting
    ball is lit by every pre-impact flash and saturates. Not photorealistic, but
    geometrically faithful.
    """
    rng = rng or np.random.default_rng(0)
    img = np.zeros((cam.height, cam.width), np.float32)
    Kinv = np.linalg.inv(cam.K)
    cos_dot = np.cos(dot_diameter_m / 2 / BALL_RADIUS_M)
    o = cam.center
    offs = (np.arange(supersample) + 0.5) / supersample - 0.5
    for i in range(len(state.flash_times_s)):
        c = state.ball_centers[i]
        uv, depth = cam.project(c[None])
        if depth[0] <= 0:
            continue
        r_px = cam.K[0, 0] * BALL_RADIUS_M / depth[0]
        u0, v0 = uv[0]
        x0, x1 = int(max(u0 - r_px - 3, 0)), int(min(u0 + r_px + 4, cam.width))
        y0, y1 = int(max(v0 - r_px - 3, 0)), int(min(v0 + r_px + 4, cam.height))
        if x0 >= x1 or y0 >= y1:
            continue
        dot_dirs = (state.ball_dots[i] - c) / BALL_RADIUS_M
        acc = np.zeros((y1 - y0, x1 - x0), np.float32)
        for dy in offs:
            for dx in offs:
                ys, xs = np.mgrid[y0:y1, x0:x1].astype(float)
                pix = np.stack([xs + dx, ys + dy, np.ones_like(xs)], -1)
                d = pix @ Kinv.T @ cam.R
                d /= np.linalg.norm(d, axis=-1, keepdims=True)
                oc = o - c
                b = d @ oc
                disc = b * b - (oc @ oc - BALL_RADIUS_M**2)
                hit = disc > 0
                sdist = -b - np.sqrt(np.where(hit, disc, 0))
                nrm = (o + sdist[..., None] * d - c) / BALL_RADIUS_M
                shade = 0.35 + 0.65 * np.clip(-(nrm * d).sum(-1), 0, 1)
                dark = (nrm @ dot_dirs.T).max(-1) > cos_dot
                acc += np.where(hit, 180.0 * shade * np.where(dark, 0.2, 1.0), 0.0)
        img[y0:y1, x0:x1] += acc / supersample**2
    img += rng.normal(8.0, noise, img.shape)
    return np.clip(img, 0, 255).astype(np.uint8)
