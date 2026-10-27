"""Strobe/exposure schedule — Python mirror of firmware/pico/src/lm_timing.c.

The Pico runs the real thing; this copy lets the simulator and solver use the
exact same flash times. tests/test_schedule_parity.py compiles the C version and
checks both agree, so change them together.

Two optical gates sit behind the ball on the target line. The club crosses
gate 1 then gate 2; from that we get club speed and predict impact time, then
place flashes so that:
  * club flashes catch the face at fixed distances before impact, and
  * ball flashes are spaced ~1.4 ball diameters apart for the *expected* ball
    speed (smash_est x club speed), so successive ball images never overlap.
All times are integer microseconds, rounded half-up (floor(x + 0.5)) to match C.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

FLASH_CLUB = 0
FLASH_BALL = 1


@dataclass
class TimingConfig:
    gate1_m: float = 0.30  # gate distance behind the ball
    gate2_m: float = 0.18
    # Club distance before impact. ~5.5 cm apart so the sticker images don't overlap in
    # either camera (they're seen at a steep angle); the last one 2 cm out for face angle.
    club_flash_m: tuple[float, ...] = (0.13, 0.075, 0.02)
    ball_spacing_m: float = 0.06
    n_ball: int = 5
    smash_est: float = 1.35
    pulse_us: int = 15
    exposure_lead_us: int = 300  # opto-isolated camera trigger: exposure start lags by tens of us
    exposure_margin_us: int = 50
    min_lead_us: int = 150  # time the Pico needs after gate 2 before the first event
    min_speed: float = 8.0
    max_speed: float = 75.0


@dataclass
class Schedule:
    ok: bool
    error: str = ""
    club_speed: float = 0.0
    t_impact_us: int = 0
    flashes: list[tuple[int, int]] = field(default_factory=list)  # (t_us, kind)
    exposure_start_us: int = 0
    exposure_end_us: int = 0


def _r(x: float) -> int:
    return int(math.floor(x + 0.5))


def compute_schedule(cfg: TimingConfig, t1_us: int, t2_us: int) -> Schedule:
    dt = t2_us - t1_us
    if dt <= 0:
        return Schedule(ok=False, error="gate order")
    v = (cfg.gate1_m - cfg.gate2_m) / (dt * 1e-6)
    if not (cfg.min_speed <= v <= cfg.max_speed):
        return Schedule(ok=False, error="speed out of range", club_speed=v)

    t_impact = t2_us + _r(cfg.gate2_m / v * 1e6)
    earliest = t2_us + cfg.min_lead_us + cfg.exposure_lead_us
    flashes: list[tuple[int, int]] = []
    for d in cfg.club_flash_m:
        t = t_impact - _r(d / v * 1e6)
        if t >= earliest:  # too-fast swings drop the earliest club flash rather than fail
            flashes.append((t, FLASH_CLUB))
    if not flashes:
        return Schedule(ok=False, error="no club flash fits", club_speed=v)

    ball_dt = _r(cfg.ball_spacing_m / (cfg.smash_est * v) * 1e6)
    for k in range(cfg.n_ball):
        flashes.append((t_impact + (k + 1) * ball_dt, FLASH_BALL))

    return Schedule(
        ok=True,
        club_speed=v,
        t_impact_us=t_impact,
        flashes=flashes,
        exposure_start_us=flashes[0][0] - cfg.exposure_lead_us,
        exposure_end_us=flashes[-1][0] + cfg.pulse_us + cfg.exposure_margin_us,
    )
