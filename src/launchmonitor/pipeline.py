"""One shot, end to end: frames + Pico report -> ShotResult. Plus saving/replaying shots.

Every shot is saved (frames as lossless PNG + JSON) so problems can be reproduced
and fixed offline, without the hardware: `python -m launchmonitor replay shots/<id>`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from .camera import triangulate
from .detect import detect_shot
from .dots import label_dots
from .models import ShotObservation, ShotResult
from .pico_link import PicoShot
from .rig import Rig
from .solver import solve


def undistort_observation(obs: ShotObservation, rig: Rig) -> ShotObservation:
    cams = {c.name: c for c in rig.cameras}
    dets = [replace(d, uv=cams[d.camera].undistort(d.uv)[0]) if d.camera in cams else d for d in obs.detections]
    return ShotObservation(obs.flash_times_s, obs.flash_kinds, dets)


# Ball centres from both cameras should meet at one 3D point. A median reprojection error above
# this means the cameras no longer match the calibration (bumped, mount loosened): recalibrate.
STEREO_WARN_PX = 1.5


def stereo_error_px(obs: ShotObservation, rig: Rig) -> float | None:
    """Median reprojection error of triangulated ball centres (undistorted detections)."""
    cams = {c.name: c for c in rig.ball_cams}
    by_flash: dict[int, list] = {}
    for d in obs.detections:
        if d.kind == "ball" and d.camera in cams:
            by_flash.setdefault(d.flash, []).append(d)
    errs = []
    for dets in by_flash.values():
        if len(dets) < 2:
            continue
        X = triangulate([cams[d.camera] for d in dets], [d.uv for d in dets])
        errs += [float(np.linalg.norm(cams[d.camera].project(X[None])[0][0] - d.uv)) for d in dets]
    return float(np.median(errs)) if errs else None


def process_shot(frames: dict[str, np.ndarray], pico: PicoShot, rig: Rig) -> tuple[ShotObservation, ShotResult]:
    obs = detect_shot(frames, pico.flash_kinds, pico.flash_times_s)
    obs = undistort_observation(obs, rig)
    obs, _ = label_dots(obs, rig)
    result = solve(obs, rig)
    result.stereo_err_px = stereo_error_px(obs, rig)
    if result.stereo_err_px is not None and result.stereo_err_px > STEREO_WARN_PX:
        result.warnings.append(
            f"cameras disagree by {result.stereo_err_px:.1f} px: a camera may have moved, re-run the calibration"
        )
    return obs, result


def save_shot(root: str | Path, frames: dict[str, np.ndarray], pico: PicoShot, result: ShotResult | None,
              extra: dict | None = None) -> Path:
    d = Path(root) / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    d.mkdir(parents=True)
    for name, img in frames.items():
        cv2.imwrite(str(d / f"{name}.png"), img)
    data = {"pico": asdict(pico), "result": asdict(result) if result else None, **(extra or {})}
    (d / "shot.json").write_text(json.dumps(data, indent=1, default=float) + "\n")
    return d


def load_shot(d: str | Path) -> tuple[dict[str, np.ndarray], PicoShot, dict]:
    d = Path(d)
    data = json.loads((d / "shot.json").read_text())
    p = data["pico"]
    pico = PicoShot(p["club_speed_mps"], p["flash_times_s"], p["flash_kinds"], tuple(p["exposure_s"]))
    frames = {f.stem: cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) for f in sorted(d.glob("*.png"))}
    return frames, pico, data
