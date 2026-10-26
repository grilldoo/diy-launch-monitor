"""Monte Carlo accuracy study: 2-camera vs 4-camera rig on simulated shots.

    python tools/accuracy_study.py [--seeds 100] [--noise 0.15]

Reports 1-sigma error per metric. Detection noise is the only error source
modelled; calibration and timing errors (likely dominant in practice) are not.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from launchmonitor.models import MPS_TO_MPH, ShotTruth  # noqa: E402
from launchmonitor.rig import four_camera_rig, two_camera_rig  # noqa: E402
from launchmonitor.sim import simulate  # noqa: E402
from launchmonitor.solver import solve  # noqa: E402

SHOTS = {
    "driver": ShotTruth(70.0, 11.0, 1.5, 2600, -300, 50.0, 2.0, -1.0, 1.0, 13.0),
    "7-iron": ShotTruth(53.0, 16.5, -2.0, 7000, 450, 39.0, -3.0, -4.5, -2.0, 21.0),
    "wedge": ShotTruth(40.0, 27.0, 0.5, 9500, 200, 33.0, 1.0, -6.0, 1.5, 38.0),
}
METRICS = ["ball mph", "VLA", "HLA", "spin %", "axis", "club mph", "path", "attack", "face", "loft"]


def errors(t: ShotTruth, r) -> list[float]:
    total = np.hypot(t.backspin_rpm, t.sidespin_rpm)
    return [
        r.ball_speed_mph - t.ball_speed_mps * MPS_TO_MPH,
        r.vla_deg - t.vla_deg,
        r.hla_deg - t.hla_deg,
        100 * (r.total_spin_rpm - total) / total,
        r.spin_axis_deg - np.degrees(np.arctan2(t.sidespin_rpm, t.backspin_rpm)),
        r.club_speed_mph - t.club_speed_mps * MPS_TO_MPH,
        r.path_deg - t.path_deg,
        r.attack_deg - t.attack_deg,
        r.face_deg - t.face_deg,
        r.loft_deg - t.loft_deg,
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--noise", type=float, default=0.15, help="detection noise, pixels (1 sigma)")
    a = ap.parse_args()
    print(f"1-sigma error, {a.seeds} shots each, {a.noise} px noise (units: mph, deg, %)\n")
    print(f"{'shot':8} {'rig':9}" + "".join(f"{m:>9}" for m in METRICS))
    for name, t in SHOTS.items():
        for rig in (two_camera_rig(), four_camera_rig()):
            E = np.array([errors(t, solve(simulate(t, rig, seed=s, pixel_noise=a.noise, impact_error_s=80e-6)[0], rig, with_carry=False)) for s in range(a.seeds)])
            print(f"{name:8} {rig.meta['name']:9}" + "".join(f"{v:9.2f}" for v in np.sqrt((E**2).mean(axis=0))))


if __name__ == "__main__":
    main()
