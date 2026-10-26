"""Shot data types. Internal maths is SI (m, s, rad); reported results use golf units."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

MPS_TO_MPH = 2.236936
RADPS_TO_RPM = 60.0 / (2.0 * np.pi)
M_TO_YD = 1.093613

BALL_RADIUS_M = 0.021335


@dataclass
class ShotTruth:
    """Launch conditions used to generate a synthetic shot (sign conventions as in docs/design.md)."""

    ball_speed_mps: float
    vla_deg: float  # vertical launch angle, + up
    hla_deg: float  # horizontal launch angle, + right of target
    backspin_rpm: float
    sidespin_rpm: float  # + curves right
    club_speed_mps: float
    path_deg: float  # + in-to-out (right)
    attack_deg: float  # + up
    face_deg: float  # face to target, + open (right)
    loft_deg: float  # dynamic loft


@dataclass
class Detection:
    camera: str
    flash: int  # index into ShotObservation.flash_times_s
    kind: str  # "ball" (centre), "dot" (ball marking), "marker" (club sticker)
    id: int  # dot / marker id; 0 for ball centres
    uv: np.ndarray


@dataclass
class ShotObservation:
    flash_times_s: list[float]  # relative to predicted impact
    flash_kinds: list[int]  # schedule.FLASH_CLUB / FLASH_BALL
    detections: list[Detection] = field(default_factory=list)


@dataclass
class ShotResult:
    ball_speed_mph: float | None = None
    vla_deg: float | None = None
    hla_deg: float | None = None
    total_spin_rpm: float | None = None
    backspin_rpm: float | None = None
    sidespin_rpm: float | None = None
    spin_axis_deg: float | None = None
    club_speed_mph: float | None = None
    path_deg: float | None = None
    attack_deg: float | None = None
    face_deg: float | None = None
    loft_deg: float | None = None
    carry_yd: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def face_to_path_deg(self) -> float | None:
        if self.face_deg is None or self.path_deg is None:
            return None
        return self.face_deg - self.path_deg

    @property
    def smash(self) -> float | None:
        if not self.ball_speed_mph or not self.club_speed_mph:
            return None
        return self.ball_speed_mph / self.club_speed_mph
