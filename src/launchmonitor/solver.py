"""Shot solver: 2D detections from N cameras -> ball, spin and club data.

Steps:
  1. triangulate every detection seen by >= 2 cameras in the same flash
  2. ball: straight-line fit of ball centres over the post-impact flashes
  3. spin: Kabsch rotation of the marking dots between consecutive ball flashes
  4. club: plane fit of face markers (face angle, loft) + line fit of their
     centroid over the pre-impact flashes (club speed, path, attack angle)
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from . import geometry as g
from .camera import Camera, triangulate
from .flight import carry_distance
from .models import MPS_TO_MPH, RADPS_TO_RPM, ShotObservation, ShotResult
from .rig import Rig
from .schedule import FLASH_BALL, FLASH_CLUB
from .markers import FACE_MARKERS_UV

MIN_COMMON_DOTS = 4
# Triangulated sticker dots must match the printed layout this closely (rms), or the face is not reported.
MAX_STICKER_FIT_M = 0.0015


def _triangulated(obs: ShotObservation, cams: dict[str, Camera], kind: str) -> dict[tuple[int, int], np.ndarray]:
    groups: dict[tuple[int, int], list] = defaultdict(list)
    for d in obs.detections:
        if d.kind == kind and d.camera in cams:
            groups[(d.flash, d.id)].append(d)
    out = {}
    for key, dets in groups.items():
        if len(dets) >= 2:
            out[key] = triangulate([cams[d.camera] for d in dets], [d.uv for d in dets])
    return out


def solve(obs: ShotObservation, rig: Rig, with_carry: bool = True) -> ShotResult:
    res = ShotResult()
    cams = {c.name: c for c in rig.cameras}
    times = np.asarray(obs.flash_times_s)

    # --- Ball launch ---------------------------------------------------------
    centers = _triangulated(obs, cams, "ball")
    ball_flashes = sorted(f for (f, _) in centers if obs.flash_kinds[f] == FLASH_BALL)
    v_ball = None
    if len(ball_flashes) >= 2:
        P = np.array([centers[(f, 0)] for f in ball_flashes])
        _, v_ball = g.fit_line(times[ball_flashes], P)
        res.ball_speed_mph = float(np.linalg.norm(v_ball) * MPS_TO_MPH)
        res.hla_deg, res.vla_deg = g.angles(v_ball)
    else:
        res.warnings.append("ball not seen in two or more flashes")

    # --- Spin ------------------------------------------------------------------
    if v_ball is not None:
        dots = _triangulated(obs, cams, "dot")
        per_flash: dict[int, dict[int, np.ndarray]] = defaultdict(dict)
        for (f, i), X in dots.items():
            if f in ball_flashes:
                per_flash[f][i] = X - centers[(f, 0)]
        omegas, weights = [], []
        for a, b in zip(ball_flashes, ball_flashes[1:]):
            common = sorted(set(per_flash[a]) & set(per_flash[b]))
            if len(common) < MIN_COMMON_DOTS:
                continue
            A = np.array([per_flash[a][i] for i in common])
            B = np.array([per_flash[b][i] for i in common])
            R = g.kabsch(A, B)
            omegas.append(g.matrix_to_rotvec(R) / (times[b] - times[a]))
            weights.append(len(common))
        if omegas:
            w = np.average(np.array(omegas), axis=0, weights=weights)
            right, up = g.spin_frame(v_ball / np.linalg.norm(v_ball))
            res.backspin_rpm = float(w @ right * RADPS_TO_RPM)
            res.sidespin_rpm = float(-(w @ up) * RADPS_TO_RPM)
            res.total_spin_rpm = float(np.linalg.norm(w) * RADPS_TO_RPM)
            res.spin_axis_deg = float(np.degrees(np.arctan2(res.sidespin_rpm, res.backspin_rpm)))
        else:
            res.warnings.append("not enough marking dots tracked for spin")

    # --- Club --------------------------------------------------------------------
    markers = _triangulated(obs, cams, "marker")
    by_flash: dict[int, dict[int, np.ndarray]] = defaultdict(dict)
    for (f, i), X in markers.items():
        if obs.flash_kinds[f] == FLASH_CLUB:
            by_flash[f][i] = X
    club_flashes = sorted(f for f, m in by_flash.items() if len(m) >= 3)
    if club_flashes:
        # Face orientation from the flash nearest impact (the face is still closing
        # before that, so averaging earlier flashes would bias it open). Fitting the
        # known sticker layout is better conditioned than a free plane fit.
        last = by_flash[club_flashes[-1]]
        ids = sorted(last)
        model = np.column_stack([FACE_MARKERS_UV[ids], np.zeros(len(ids))])
        pts = np.array([last[i] for i in ids])
        R = g.kabsch(model - model.mean(axis=0), pts - pts.mean(axis=0))
        fit_rms = float(np.sqrt(np.mean(np.sum(((model - model.mean(axis=0)) @ R.T - (pts - pts.mean(axis=0))) ** 2, axis=1))))
        if fit_rms > MAX_STICKER_FIT_M:  # 3D dots don't match the sticker: a label or match went wrong
            res.warnings.append(f"club sticker fit off by {fit_rms * 1000:.1f} mm: face angle and loft not reported")
        else:
            n = R @ np.array([0.0, 0.0, -1.0])  # face (u=toe, v=up) is left-handed w.r.t. its normal
            res.face_deg, res.loft_deg = g.angles(n)
        # Path from the motion of markers common to every club flash.
        common = set.intersection(*(set(by_flash[f]) for f in club_flashes))
        if len(club_flashes) >= 2 and common:
            C = np.array([np.mean([by_flash[f][i] for i in common], axis=0) for f in club_flashes])
            _, v_club = g.fit_line(times[club_flashes], C)
            res.club_speed_mph = float(np.linalg.norm(v_club) * MPS_TO_MPH)
            res.path_deg, res.attack_deg = g.angles(v_club)
        else:
            res.warnings.append("club seen in only one flash: no path / speed")
    else:
        res.warnings.append("club markers not seen")

    if with_carry and res.ball_speed_mph is not None and res.backspin_rpm is not None:
        res.carry_yd = carry_distance(res)
    return res

