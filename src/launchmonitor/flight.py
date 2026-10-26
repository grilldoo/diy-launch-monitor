"""Simple ball-flight model for the stand-alone readout.

GSPro computes its own flight from launch data, so this only has to be roughly
right. Lift/drag vs spin factor follow the common quadratic fits used by hobby
simulators; coefficients are tuned so tour-average driver and 7-iron launches
land near published carry numbers (see tests/test_flight.py).
"""

from __future__ import annotations

import numpy as np

from . import geometry as g
from .models import BALL_RADIUS_M, M_TO_YD, MPS_TO_MPH, ShotResult

RHO = 1.204  # kg/m^3, sea level 20 C
MASS = 0.04593
AREA = np.pi * BALL_RADIUS_M**2
GRAVITY = np.array([0.0, -9.81, 0.0])
SPIN_DECAY_TAU_S = 25.0


def _coefficients(spin_factor: float) -> tuple[float, float]:
    s = min(spin_factor, 0.5)
    cd = 0.17 + 0.40 * s
    cl = max(1.6 * s - 2.0 * s * s, 0.0)
    return cd, cl


def simulate_flight(speed_mps: float, vla_deg: float, hla_deg: float, back_rpm: float, side_rpm: float, dt: float = 0.002):
    v = speed_mps * g.direction(hla_deg, vla_deg)
    right, up = g.spin_frame(v / speed_mps)
    w = (back_rpm * right - side_rpm * up) * (2 * np.pi / 60)
    p = np.zeros(3)
    t = 0.0
    path = [p.copy()]
    k = 0.5 * RHO * AREA / MASS
    while True:
        speed = np.linalg.norm(v)
        wt = w * np.exp(-t / SPIN_DECAY_TAU_S)
        cd, cl = _coefficients(BALL_RADIUS_M * np.linalg.norm(wt) / speed)
        lift_dir = np.cross(wt, v)
        n = np.linalg.norm(lift_dir)
        lift_dir = lift_dir / n if n > 0 else lift_dir
        a = GRAVITY - k * cd * speed * v + k * cl * speed**2 * lift_dir
        v = v + a * dt
        p = p + v * dt
        t += dt
        path.append(p.copy())
        if p[1] < 0 or t > 20:
            break
    return np.array(path)


def carry_distance(res: ShotResult) -> float:
    path = simulate_flight(
        res.ball_speed_mph / MPS_TO_MPH, res.vla_deg, res.hla_deg, res.backspin_rpm, res.sidespin_rpm or 0.0
    )
    return float(np.hypot(path[-1, 0], path[-1, 2]) * M_TO_YD)
