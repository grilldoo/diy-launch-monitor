"""Build-time calibration from rendered ChArUco images (with lens distortion), then
board-free setups: IMU level + reference-edge aim must reproduce the true world frame."""

import numpy as np
import pytest

from launchmonitor import geometry as g
from launchmonitor.calibration import (WORLD_FROM_BOARD, Board, calibrate_from_images, load_calibration, reaim,
                                       save_calibration)
from launchmonitor.camera import Camera
from launchmonitor.models import MPS_TO_MPH, ShotTruth
from launchmonitor.pipeline import process_shot
from launchmonitor.pico_link import PicoShot
from launchmonitor.rig import BALL_PAIR_TARGET, Rig, two_camera_rig
from launchmonitor.sim import render, render_board, shot_state

DIST = np.array([-0.12, 0.05, 0.0005, -0.0003, 0.0])
# A deliberately sloppy IMU mounting (about 30 deg twisted), offset and noise, in g.
R_UNIT_IMU_TRUE = g.rotvec_to_matrix(np.array([0.05, -0.08, 0.5]))
BIAS_G = np.array([0.004, -0.003, 0.006])
NOISE_G = 0.0005


def _rot(axis, deg):
    return g.rotvec_to_matrix(np.asarray(axis, float) * np.radians(deg))


def _true_rig():
    rig = two_camera_rig()
    for c in rig.cameras:
        c.dist = DIST.copy()
    return rig


def tilt_rig(rig: Rig, R_t: np.ndarray) -> Rig:
    """The whole unit physically rotated by R_t (world frame) about camera A."""
    p = rig.ball_cams[0].center
    cams = []
    for c in rig.cameras:
        R = c.R @ R_t.T
        center = p + R_t @ (c.center - p)
        cams.append(Camera(c.name, c.K, R, -R @ center, c.width, c.height, c.dist))
    return Rig(ball_cams=cams, club_cams=cams, meta=dict(rig.meta))


def accel_for(rig: Rig, rng) -> np.ndarray:
    up_unit = rig.ball_cams[0].R @ np.array([0.0, 1.0, 0.0])
    return R_UNIT_IMU_TRUE.T @ up_unit + BIAS_G + rng.normal(0, NOISE_G, 3)


def true_world_from_unit(rig: Rig) -> np.ndarray:
    return rig.ball_cams[0].R.T  # X_unit = R_A X_world (t aside)


def angle_deg(Ra, Rb):
    return float(np.degrees(np.linalg.norm(g.matrix_to_rotvec(Ra @ Rb.T))))


@pytest.fixture(scope="module")
def build():
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
        pairs.append(tuple(render_board(cam, board, R, c - R @ np.array([W / 2, H / 2, 0]), rng) for cam in rig.cameras))
    # Board upright, parallel to the reference edge (= world +x at build), facing the unit.
    origin = np.array([-0.12, -0.0213 + H + board.square_m, -0.06])
    edge = tuple(render_board(cam, board, WORLD_FROM_BOARD.T, origin, rng) for cam in rig.cameras)
    tilts = []
    for R_t in [np.eye(3), _rot([0, 0, 1], 5), _rot([0, 0, 1], -5), _rot([1, 0, 0], 5), _rot([1, 0, 0], -5)]:
        t_rig = tilt_rig(rig, R_t)
        tilts.append((render_board(t_rig.ball_cams[0], board, WORLD_FROM_BOARD.T, origin, rng), accel_for(t_rig, rng)))
    cal, report = calibrate_from_images(pairs, edge, board, tilts=tilts)
    return rig, cal, report, board


def test_report(build):
    _, _, report, _ = build
    assert report["camA_rms_px"] < 0.3 and report["camB_rms_px"] < 0.3 and report["stereo_rms_px"] < 0.3
    assert report["baseline_mm"] == pytest.approx(200.0, abs=0.5)
    assert report["imu_rms_deg"] < 0.1 and "warning" not in report


def test_unit_frame_cameras_edge_and_up(build):
    true, cal, _, _ = build
    A, B = true.ball_cams
    a, b = cal.cams
    for t, c in ((A, a), (B, b)):
        assert c.K[0, 0] == pytest.approx(t.K[0, 0], rel=0.005)
        assert c.dist[0] == pytest.approx(DIST[0], abs=0.02)
    assert angle_deg(b.R, B.R @ A.R.T) < 0.1  # B relative to A
    assert np.linalg.norm(b.center - A.R @ (B.center - A.center)) < 0.002
    edge_true = A.R @ np.array([1.0, 0, 0])
    up_true = A.R @ np.array([0, 1.0, 0])
    assert np.degrees(np.arccos(cal.edge_unit @ edge_true)) < 0.1
    assert np.degrees(np.arccos(cal.up_unit_build @ up_true)) < 0.1


@pytest.mark.parametrize("pitch,roll", [(0.0, 0.0), (3.0, -2.0), (-4.0, 4.0)])
def test_board_free_setup_matches_truth(build, pitch, roll):
    """New setup: unit on a sloping mat, reference edge lined up with the target."""
    true, cal, _, _ = build
    # Pitch about z then roll about x keeps the edge's horizontal direction on the target line.
    setup = tilt_rig(true, _rot([0, 0, 1], pitch) @ _rot([1, 0, 0], roll))
    acc = accel_for(setup, np.random.default_rng(42))
    R_wu = cal.world_from_imu(acc)
    assert angle_deg(R_wu, true_world_from_unit(setup)) < 0.2
    assert cal.tilt_deg(acc) == pytest.approx(np.hypot(pitch, roll), abs=0.3)


def test_shot_on_tilted_mat_end_to_end(build):
    true, cal, _, _ = build
    setup = tilt_rig(true, _rot([0, 0, 1], 3.0) @ _rot([1, 0, 0], -2.0))
    rig = cal.rig(cal.world_from_imu(accel_for(setup, np.random.default_rng(7))))
    t = ShotTruth(62.0, 13.0, 1.5, 3200, -400, 45.0, 1.0, -2.0, 0.5, 14.0)
    q = np.array([0.4, 0.2, -0.7])
    st = shot_state(t, initial_orientation=g.rotvec_to_matrix(q / np.linalg.norm(q) * 1.5))
    frames = {c.name: render(st, c, np.random.default_rng(5)) for c in setup.ball_cams}
    _, r = process_shot(frames, PicoShot(t.club_speed_mps, st.flash_times_s, st.flash_kinds, (0, 0)), rig)
    assert r.ball_speed_mph == pytest.approx(t.ball_speed_mps * MPS_TO_MPH, abs=0.6)
    assert r.vla_deg == pytest.approx(t.vla_deg, abs=0.35)
    assert r.hla_deg == pytest.approx(t.hla_deg, abs=0.35)
    assert r.total_spin_rpm == pytest.approx(np.hypot(t.backspin_rpm, t.sidespin_rpm), rel=0.04)
    assert r.stereo_err_px < 0.8 and not any("cameras disagree" in w for w in r.warnings)


def test_bumped_camera_is_flagged(build):
    true, cal, _, _ = build
    rig = cal.rig(cal.R_world_unit_board)
    t = ShotTruth(55.0, 15.0, 0.0, 4000, 0, 40.0, 0.0, -3.0, 0.0, 18.0)
    st = shot_state(t)
    frames = {c.name: render(st, c, np.random.default_rng(1)) for c in true.ball_cams}
    pico = PicoShot(t.club_speed_mps, st.flash_times_s, st.flash_kinds, (0, 0))
    b = rig.ball_cams[1]
    b.R = _rot([1, 0, 0], 0.4) @ b.R  # camera B knocked by 0.4 deg since calibration
    _, r = process_shot(frames, pico, rig)
    assert r.stereo_err_px > 1.5 and any("cameras disagree" in w for w in r.warnings)


def test_save_load_and_reaim(build, tmp_path):
    true, cal, _, board = build
    save_calibration(cal, tmp_path / "cal.json")
    back = load_calibration(tmp_path / "cal.json")
    for a, b in zip(cal.cams, back.cams):
        assert np.allclose(a.K, b.K) and np.allclose(a.R, b.R) and np.allclose(a.dist, b.dist)
    assert np.allclose(back.R_unit_imu, cal.R_unit_imu) and np.allclose(back.edge_unit, cal.edge_unit)
    # Optional board aim after moving the unit (unit yawed 2 deg and tilted; board marks the target line).
    setup = tilt_rig(true, _rot([0, 1, 0], 2.0) @ _rot([1, 0, 0], 3.0))
    H = board.size_m[1]
    img = render_board(setup.ball_cams[0], board, WORLD_FROM_BOARD.T, np.array([-0.1, -0.02 + H, -0.1]),
                       np.random.default_rng(9))
    re = reaim(back, img, board)
    assert angle_deg(re.R_world_unit_board, true_world_from_unit(setup)) < 0.15
