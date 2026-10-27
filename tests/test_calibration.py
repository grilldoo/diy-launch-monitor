"""Calibration from rendered ChArUco images (with lens distortion) recovers the true rig."""

import numpy as np
import pytest

from launchmonitor import geometry as g
from launchmonitor.calibration import WORLD_FROM_BOARD, Board, calibrate_from_images, load_rig, reaim, save_rig
from launchmonitor.rig import BALL_PAIR_TARGET, two_camera_rig
from launchmonitor.sim import render_board

DIST = np.array([-0.12, 0.05, 0.0005, -0.0003, 0.0])


def _true_rig():
    rig = two_camera_rig()
    for c in rig.cameras:
        c.dist = DIST.copy()
    return rig


def _aim_origin(board, dz=-0.06):
    W, H = board.size_m
    return np.array([-0.12, -0.0213 + H + board.square_m, dz])


@pytest.fixture(scope="module")
def calibrated():
    rig, board = _true_rig(), Board()
    rng = np.random.default_rng(0)
    W, H = board.size_m
    center = np.mean([c.center for c in rig.cameras], axis=0)
    pairs = []
    for _ in range(12):
        c = BALL_PAIR_TARGET + rng.uniform(-0.12, 0.12, 3) * [1, 0.6, 1] + [0, 0.08, 0]
        n = (center - c) / np.linalg.norm(center - c)
        z = g.rotvec_to_matrix(rng.normal(0, 0.35, 3)) @ (-n)
        x = np.cross([0, -1, 0], z)
        x /= np.linalg.norm(x)
        R = np.column_stack([x, np.cross(z, x), z])
        t = c - R @ np.array([W / 2, H / 2, 0])
        pairs.append(tuple(render_board(cam, board, R, t, rng) for cam in rig.ball_cams))
    origin = _aim_origin(board)
    aim = tuple(render_board(cam, board, WORLD_FROM_BOARD.T, origin, rng) for cam in rig.ball_cams)
    cal, report = calibrate_from_images(pairs, aim, board)
    return rig, cal, report, origin, board


def test_reprojection_and_baseline(calibrated):
    _, _, report, _, _ = calibrated
    assert report["camA_rms_px"] < 0.3 and report["camB_rms_px"] < 0.3 and report["stereo_rms_px"] < 0.3
    assert report["baseline_mm"] == pytest.approx(200.0, abs=0.5)


def test_recovers_intrinsics_and_world_pose(calibrated):
    true, cal, _, origin, _ = calibrated
    for t, c in zip(true.ball_cams, cal.ball_cams):
        assert c.K[0, 0] == pytest.approx(t.K[0, 0], rel=0.005)
        assert c.dist[0] == pytest.approx(DIST[0], abs=0.02)
        # World origin is the aim board's corner, so compare positions relative to it.
        assert np.linalg.norm(c.center - (t.center - origin)) < 0.002
        assert np.degrees(np.linalg.norm(g.matrix_to_rotvec(c.R @ t.R.T))) < 0.15  # angles drive VLA/HLA


def test_save_load_and_reaim(calibrated, tmp_path):
    true, cal, _, _, board = calibrated
    save_rig(cal, tmp_path / "cal.json")
    back = load_rig(tmp_path / "cal.json")
    for a, b in zip(cal.cameras, back.cameras):
        assert np.allclose(a.K, b.K) and np.allclose(a.R, b.R) and np.allclose(a.dist, b.dist)
    # Unit moved: aim board now 4 cm further from the ball line. Rotations must not change.
    origin2 = _aim_origin(board, dz=-0.10)
    img = render_board(true.ball_cams[0], board, WORLD_FROM_BOARD.T, origin2, np.random.default_rng(9))
    re = reaim(back, img, board)
    for t, c in zip(true.ball_cams, re.ball_cams):
        assert np.linalg.norm(c.center - (t.center - origin2)) < 0.003
        assert np.degrees(np.linalg.norm(g.matrix_to_rotvec(c.R @ t.R.T))) < 0.15
