"""Club data from pixels: rendered frames with the face sticker -> detection -> labels -> solver."""

import itertools

import numpy as np
import pytest

from launchmonitor.detect import assign_flash_steps, label_sticker
from launchmonitor.markers import FACE_MARKERS_UV, STICKER_RECT
from launchmonitor.models import MPS_TO_MPH, ShotTruth
from launchmonitor.pico_link import PicoShot
from launchmonitor.pipeline import process_shot
from launchmonitor.rig import two_camera_rig
from launchmonitor.sim import render, shot_state
from launchmonitor.sim_source import SimulatedLaunchMonitor

SHOTS = {
    "driver": ShotTruth(70.0, 11.0, 1.5, 2600, -300, 50.0, 2.0, -1.0, 1.0, 13.0),
    "7-iron": ShotTruth(53.0, 16.5, -2.0, 7000, 450, 39.0, -3.0, -4.5, -2.0, 21.0),
    "wedge": ShotTruth(40.0, 27.0, 0.5, 9500, 200, 33.0, 1.0, -6.0, 1.5, 38.0),  # slow: sticker images touch
}


def _best_wrong_affine_fit_mm(M):
    """Smallest rms (mm) with which any *wrong* front-view (non-mirror) assignment of the
    dots fits the layout under an affine map, with all dots or any one missing."""
    worst = np.inf
    n = len(M)
    for miss in [None, *range(n)]:
        obs_ids = [i for i in range(n) if i != miss]
        obs = M[obs_ids]
        for model_ids in itertools.permutations(range(n), len(obs_ids)):
            if list(model_ids) == obs_ids:
                continue
            A = np.column_stack([M[list(model_ids)], np.ones(len(obs_ids))])
            coef, *_ = np.linalg.lstsq(A, obs, rcond=None)
            if np.linalg.det(coef[:2, :2]) <= 0:
                continue
            worst = min(worst, float(np.sqrt(np.mean(np.sum((A @ coef - obs) ** 2, axis=1)))))
    return worst


def test_layout_is_unambiguous():
    M = FACE_MARKERS_UV * 1000
    assert _best_wrong_affine_fit_mm(M) > 1.0  # no wrong labelling fits, however obliquely seen
    d = [np.linalg.norm(M[i] - M[j]) for i, j in itertools.combinations(range(len(M)), 2)]
    assert min(d) >= 9.0  # 5 mm dots stay well apart
    u0, v0, u1, v1 = STICKER_RECT
    assert u0 >= 0.003  # clear of a centred strike
    assert u1 <= 0.037 and v1 - v0 <= 0.03  # fits on the toe side of an iron face


@pytest.mark.parametrize("missing", [None, 0, 2, 4])
def test_label_sticker_recovers_ids_under_a_steep_view(missing):
    rng = np.random.default_rng(1)
    for _ in range(20):
        # Random front-facing affine view (foreshortened ~0.4x on one axis) plus a little noise.
        th = rng.uniform(0, 2 * np.pi)
        R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        S = np.diag([2.7, 2.7 * rng.uniform(0.35, 1.0)])
        A = R @ S  # front view: no mirror (matches the real projections, see label_sticker)
        P = (FACE_MARKERS_UV * 1000) @ A.T + rng.uniform(100, 900, 2) + rng.normal(0, 0.2, (5, 2))
        keep = [i for i in range(5) if i != missing]
        order = rng.permutation(keep)
        got = label_sticker([P[i] for i in order], FACE_MARKERS_UV)
        assert got is not None
        for mid, uv in got.items():
            assert np.allclose(uv, P[mid])


def test_label_sticker_rejects_a_mirror_image():
    P = (FACE_MARKERS_UV * 1000) @ np.diag([2.7, -2.7]).T + 300  # mirrored: as if seen from behind
    assert label_sticker(list(P), FACE_MARKERS_UV) is None


def test_flash_steps_survive_missing_images():
    assert assign_flash_steps([60, 121, 183, 246, 310], 5) == [0, 1, 2, 3, 4]
    assert assign_flash_steps([121, 183, 246, 310], 5) == [1, 2, 3, 4]  # first image hidden
    assert assign_flash_steps([60, 183, 246], 5) == [0, 2, 3]
    assert assign_flash_steps([60, 90, 183], 5) is None  # nonsense spacing: refuse


@pytest.mark.parametrize("name", SHOTS)
def test_club_data_from_pixels(name):
    t = SHOTS[name]
    rig = two_camera_rig()
    st = shot_state(t)
    frames = {c.name: render(st, c, np.random.default_rng(2)) for c in rig.ball_cams}
    obs, r = process_shot(frames, PicoShot(t.club_speed_mps, st.flash_times_s, st.flash_kinds, (0, 0)), rig)
    markers = [d for d in obs.detections if d.kind == "marker"]
    assert len(markers) >= 25  # 3 flashes x 2 cameras x 5 dots, minus the odd hidden dot
    cams = {c.name: c for c in rig.ball_cams}
    for d in markers:  # every label is the right dot
        assert np.linalg.norm(cams[d.camera].project(st.club_markers[d.flash][d.id][None])[0][0] - d.uv) < 1.5
    assert not r.warnings, r.warnings
    assert r.club_speed_mph == pytest.approx(t.club_speed_mps * MPS_TO_MPH, abs=0.5)
    assert r.path_deg == pytest.approx(t.path_deg, abs=0.4)
    assert r.attack_deg == pytest.approx(t.attack_deg, abs=0.2)
    assert r.face_deg == pytest.approx(t.face_deg, abs=1.0)
    assert r.loft_deg == pytest.approx(t.loft_deg, abs=1.5)


def test_random_shots_never_report_wrong_club_data():
    """Missing club data is acceptable; wrong club data is not."""
    rig = two_camera_rig()
    sim = SimulatedLaunchMonitor(rig, seed=29)
    reported = 0
    for _ in range(12):
        pico = sim.read_shot()
        t = sim.last_truth
        _, r = process_shot(sim.collect(), pico, rig)
        if r.face_deg is not None:
            reported += 1
            assert r.face_deg == pytest.approx(t.face_deg, abs=1.0)
            assert r.loft_deg == pytest.approx(t.loft_deg, abs=1.5)
        if r.path_deg is not None:
            assert r.path_deg == pytest.approx(t.path_deg, abs=0.5)
    assert reported >= 10
