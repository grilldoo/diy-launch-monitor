"""End-to-end: synthetic shot -> observations -> solver recovers the launch conditions."""

import numpy as np
import pytest

from launchmonitor.models import MPS_TO_MPH, ShotTruth
from launchmonitor.rig import four_camera_rig, two_camera_rig
from launchmonitor.sim import simulate
from launchmonitor.solver import solve

SHOTS = {
    "driver": ShotTruth(70.0, 11.0, 1.5, 2600, -300, 50.0, 2.0, -1.0, 1.0, 13.0),
    "7-iron": ShotTruth(53.0, 16.5, -2.0, 7000, 450, 39.0, -3.0, -4.5, -2.0, 21.0),
    "wedge": ShotTruth(40.0, 27.0, 0.5, 9500, 200, 33.0, 1.0, -6.0, 1.5, 38.0),
}

# ~4 sigma at 0.15 px detection noise (sigmas from tools/accuracy_study.py).
TOL = dict(ball_mph=0.5, vla=0.3, hla=0.3, spin_frac=0.05, axis=2.0, club_mph=1.0, path=0.8, attack=0.5)
# Face/loft depend on how closely the cameras see the club: the dedicated
# 4-camera club pair is ~3x better than sharing one pair.
FACE_LOFT_TOL = {"2-camera": 2.9, "4-camera": 1.1}


@pytest.mark.parametrize("rig_fn", [two_camera_rig, four_camera_rig], ids=["2cam", "4cam"])
@pytest.mark.parametrize("name", SHOTS)
def test_recovers_launch(name, rig_fn):
    t = SHOTS[name]
    rig = rig_fn()
    obs, _ = simulate(t, rig, seed=3, impact_error_s=80e-6)
    r = solve(obs, rig)
    assert not r.warnings, r.warnings
    assert r.ball_speed_mph == pytest.approx(t.ball_speed_mps * MPS_TO_MPH, abs=TOL["ball_mph"])
    assert r.vla_deg == pytest.approx(t.vla_deg, abs=TOL["vla"])
    assert r.hla_deg == pytest.approx(t.hla_deg, abs=TOL["hla"])
    total = np.hypot(t.backspin_rpm, t.sidespin_rpm)
    assert r.total_spin_rpm == pytest.approx(total, rel=TOL["spin_frac"])
    assert r.spin_axis_deg == pytest.approx(np.degrees(np.arctan2(t.sidespin_rpm, t.backspin_rpm)), abs=TOL["axis"])
    assert r.club_speed_mph == pytest.approx(t.club_speed_mps * MPS_TO_MPH, abs=TOL["club_mph"])
    assert r.path_deg == pytest.approx(t.path_deg, abs=TOL["path"])
    assert r.attack_deg == pytest.approx(t.attack_deg, abs=TOL["attack"])
    tol = FACE_LOFT_TOL[rig.meta["name"]]
    assert r.face_deg == pytest.approx(t.face_deg, abs=tol)
    assert r.loft_deg == pytest.approx(t.loft_deg, abs=tol)


def test_noise_free_is_near_exact():
    rig = two_camera_rig()
    t = SHOTS["driver"]
    r = solve(simulate(t, rig, pixel_noise=0.0)[0], rig)
    assert r.ball_speed_mph == pytest.approx(t.ball_speed_mps * MPS_TO_MPH, abs=0.01)
    assert r.face_deg == pytest.approx(t.face_deg, abs=0.01)
    assert r.backspin_rpm == pytest.approx(t.backspin_rpm, rel=1e-3)
