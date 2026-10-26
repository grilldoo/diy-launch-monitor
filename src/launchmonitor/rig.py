"""Camera rig presets.

The unit sits on the far side of the ball from a right-handed golfer (+z),
slightly forward of the ball (+x) and yawed back toward the impact zone so the
cameras can see the club-face markers at an angle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .camera import Camera, look_at

# Tunable placement (metres, world frame).
UNIT_POSITION = np.array([0.35, 0.10, 0.60])
BALL_PAIR_TARGET = np.array([0.10, 0.03, 0.0])  # middle of the ball-flight window
CLUB_PAIR_TARGET = np.array([-0.04, 0.02, 0.0])  # last ~10 cm before impact
BASELINE_M = 0.20


@dataclass
class Rig:
    ball_cams: list[Camera]
    club_cams: list[Camera]
    meta: dict = field(default_factory=dict)

    @property
    def cameras(self) -> list[Camera]:
        # De-duplicate: in the two-camera rig the same cameras do both jobs.
        seen, out = set(), []
        for c in self.ball_cams + self.club_cams:
            if c.name not in seen:
                seen.add(c.name)
                out.append(c)
        return out


def _pair(prefix: str, center: np.ndarray, target: np.ndarray, focal_mm: float, baseline: float):
    fwd = target - center
    right = np.cross(fwd, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    a = look_at(f"{prefix}A", center - right * baseline / 2, target, focal_mm)
    b = look_at(f"{prefix}B", center + right * baseline / 2, target, focal_mm)
    return [a, b]


def two_camera_rig(baseline: float = BASELINE_M) -> Rig:
    """Stage 1: one stereo pair (6 mm lenses) sees both club and ball."""
    pair = _pair("cam", UNIT_POSITION, BALL_PAIR_TARGET, 6.0, baseline)
    return Rig(ball_cams=pair, club_cams=pair, meta={"name": "2-camera"})


def four_camera_rig(baseline: float = BASELINE_M) -> Rig:
    """Stage 2 (GC Quad-style): ball pair (6 mm) + dedicated club pair (12 mm, tighter view)."""
    ball = _pair("ball", UNIT_POSITION, BALL_PAIR_TARGET, 6.0, baseline)
    club_center = UNIT_POSITION + np.array([-0.12, 0.08, -0.10])
    club = _pair("club", club_center, CLUB_PAIR_TARGET, 12.0, baseline)
    return Rig(ball_cams=ball, club_cams=club, meta={"name": "4-camera"})
