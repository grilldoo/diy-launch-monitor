"""Ball-dot matching: unlabeled detections must get the right pattern ids."""

import numpy as np
import pytest

from launchmonitor import geometry as g
from launchmonitor.detect import detect_shot
from launchmonitor.dots import label_dots, load_pattern, sphere_points
from launchmonitor.models import BALL_RADIUS_M, MPS_TO_MPH, ShotTruth
from launchmonitor.rig import two_camera_rig
from launchmonitor.sim import render, shot_state, simulate
from launchmonitor.solver import solve

DRIVER = ShotTruth(70.0, 11.0, 1.5, 2600, -300, 50.0, 2.0, -1.0, 1.0, 13.0)
WEDGE = ShotTruth(40.0, 27.0, 0.5, 9500, 200, 33.0, 1.0, -6.0, 1.5, 38.0)


def test_pattern_is_printable():
    p = load_pattern()
    assert len(p) >= 24
    assert np.all(np.abs(np.degrees(np.arcsin(p[:, 1]))) > 5)  # clear of the jig seam
    cos = p @ p.T - 2 * np.eye(len(p))
    assert np.degrees(np.arccos(cos.max())) > 20  # dots don't touch


def test_sphere_points_round_trip():
    cam = two_camera_rig().ball_cams[0]
    c = np.array([0.15, 0.04, 0.01])
    n = np.array([[0.3, 0.2, 1.0], [0.8, 0.1, 0.6]])
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    X = c + BALL_RADIUS_M * n
    uv, _ = cam.project(X)
    assert np.allclose(sphere_points(cam, uv, c), X, atol=1e-9)


def _label_errors(obs_labeled, obs_matched):
    truth = {(d.camera, d.flash, tuple(np.round(d.uv, 6))): d.id for d in obs_labeled.detections if d.kind == "dot"}
    got = [d for d in obs_matched.detections if d.kind == "dot"]
    wrong = sum(truth[(d.camera, d.flash, tuple(np.round(d.uv, 6)))] != d.id for d in got)
    return wrong, len(truth) - len(got)


@pytest.mark.parametrize("truth", [DRIVER, WEDGE], ids=["driver", "wedge"])
def test_labels_match_truth_over_many_orientations(truth):
    rig = two_camera_rig()
    failures = 0
    for seed in range(15):
        labeled, _ = simulate(truth, rig, seed=seed)
        unlabeled = type(labeled)(labeled.flash_times_s, labeled.flash_kinds,
                                  [d if d.kind != "dot" else type(d)(d.camera, d.flash, d.kind, -1, d.uv) for d in labeled.detections])
        matched, _ = label_dots(unlabeled, rig)
        wrong, dropped = _label_errors(labeled, matched)
        failures += wrong > 0
        assert dropped <= 2
    assert failures == 0


def test_spin_from_unlabeled_matches_labeled():
    rig = two_camera_rig()
    a = solve(simulate(DRIVER, rig, seed=4)[0], rig)
    b = solve(label_dots(simulate(DRIVER, rig, seed=4, labeled=False)[0], rig)[0], rig)
    assert b.total_spin_rpm == pytest.approx(a.total_spin_rpm, rel=1e-3)
    assert b.spin_axis_deg == pytest.approx(a.spin_axis_deg, abs=0.1)


@pytest.mark.parametrize("truth", [DRIVER, WEDGE], ids=["driver", "wedge"])
def test_rendered_frames_end_to_end(truth):
    """Pixels -> ball + dot detection -> matching -> solver."""
    rig = two_camera_rig()
    q = np.array([0.3, -0.8, 0.5])
    st = shot_state(truth, initial_orientation=g.rotvec_to_matrix(q / np.linalg.norm(q) * 2.0))
    frames = {c.name: render(st, c, np.random.default_rng(5)) for c in rig.ball_cams}
    obs = detect_shot(frames, st.flash_kinds, st.flash_times_s)
    matched, fits = label_dots(obs, rig)
    assert len(fits) == 5 and all(f.n_missing == 0 for f in fits.values())
    # Every labeled detection lands on the true projection of that pattern dot. (1.5 px, not
    # less: after impact the club's sticker image can overlap a ball image and nudge a dot.)
    cams = {c.name: c for c in rig.ball_cams}
    n_dots = 0
    for d in matched.detections:
        if d.kind == "dot":
            uv, _ = cams[d.camera].project(st.ball_dots[d.flash][d.id][None])
            assert np.linalg.norm(uv[0] - d.uv) < 1.5
            n_dots += 1
    assert n_dots >= 60
    r = solve(matched, rig, with_carry=False)
    assert r.ball_speed_mph == pytest.approx(truth.ball_speed_mps * MPS_TO_MPH, abs=0.5)
    assert r.vla_deg == pytest.approx(truth.vla_deg, abs=0.3)
    assert r.hla_deg == pytest.approx(truth.hla_deg, abs=0.3)
    assert r.total_spin_rpm == pytest.approx(np.hypot(truth.backspin_rpm, truth.sidespin_rpm), rel=0.03)
    assert r.spin_axis_deg == pytest.approx(np.degrees(np.arctan2(truth.sidespin_rpm, truth.backspin_rpm)), abs=1.5)
