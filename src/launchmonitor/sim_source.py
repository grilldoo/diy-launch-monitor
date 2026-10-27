"""A simulated launch monitor: fake Pico + fake cameras, so the whole app runs off-hardware.

read_shot() invents a random but plausible shot, renders what each camera would see,
and returns the Pico's report. collect() then hands back those frames, just as the
real Pico + PiCameraSource pair would.
"""

from __future__ import annotations

import time

import numpy as np

from . import geometry as g
from .models import ShotTruth
from .pico_link import PicoShot
from .rig import Rig
from .schedule import TimingConfig
from .sim import render, shot_state


def random_truth(rng: np.random.Generator) -> ShotTruth:
    club = rng.uniform(30, 50)
    return ShotTruth(
        ball_speed_mps=club * rng.uniform(1.3, 1.48),
        vla_deg=rng.uniform(9, 28),
        hla_deg=rng.uniform(-4, 4),
        backspin_rpm=rng.uniform(2200, 8500),
        sidespin_rpm=rng.uniform(-800, 800),
        club_speed_mps=club,
        path_deg=rng.uniform(-4, 4),
        attack_deg=rng.uniform(-5, 3),
        face_deg=rng.uniform(-3, 3),
        loft_deg=rng.uniform(10, 40),
    )


class SimulatedLaunchMonitor:
    def __init__(self, rig: Rig, seed: int = 0, interval_s: float = 0.0, timing: TimingConfig | None = None):
        self.rig = rig
        self.rng = np.random.default_rng(seed)
        self.interval_s = interval_s
        self.timing = timing or TimingConfig()
        self.last_truth: ShotTruth | None = None
        self._frames: dict[str, np.ndarray] | None = None

    def read_shot(self, timeout: float = 1.0) -> PicoShot | None:
        if self.interval_s:
            time.sleep(min(self.interval_s, timeout))
        truth = random_truth(self.rng)
        q = self.rng.normal(size=3)
        R0 = g.rotvec_to_matrix(q / np.linalg.norm(q) * self.rng.uniform(0, np.pi))
        impact_err = self.rng.normal(0, 60e-6)
        st = shot_state(truth, self.timing, impact_err, initial_orientation=R0)
        self._frames = {c.name: render(st, c, self.rng) for c in self.rig.ball_cams}
        self.last_truth = truth
        return PicoShot(truth.club_speed_mps, list(st.flash_times_s), list(st.flash_kinds), (0.0, 0.0))

    def collect(self, timeout: float = 1.0) -> dict[str, np.ndarray] | None:
        frames, self._frames = self._frames, None
        return frames

    def send(self, command: str) -> None:
        pass
