"""The rig has to actually see what the solver needs."""

import pytest

from launchmonitor.rig import four_camera_rig, two_camera_rig
from launchmonitor.schedule import FLASH_BALL, FLASH_CLUB
from launchmonitor.sim import shot_state
from launchmonitor.models import ShotTruth


@pytest.mark.parametrize("rig_fn", [two_camera_rig, four_camera_rig])
@pytest.mark.parametrize("ball_mps,hla", [(75, -6), (75, 6), (30, 0)])
def test_everything_in_frame(rig_fn, ball_mps, hla):
    rig = rig_fn()
    st = shot_state(ShotTruth(ball_mps, 14, hla, 3000, 0, ball_mps / 1.4, 0, -3, 0, 15))
    for i, kind in enumerate(st.flash_kinds):
        cams, pts = (rig.ball_cams, st.ball_centers[i][None]) if kind == FLASH_BALL else (rig.club_cams, st.club_markers[i])
        for cam in cams:
            uv, depth = cam.project(pts)
            assert cam.in_image(uv, depth, margin=40).all(), (cam.name, i, uv)


def test_ball_images_do_not_overlap():
    st = shot_state(ShotTruth(45, 20, 0, 6000, 0, 45 / 1.15, 0, -4, 0, 25))  # low smash: tightest spacing
    xs = [st.ball_centers[i][0] for i, k in enumerate(st.flash_kinds) if k == FLASH_BALL]
    gaps = [b - a for a, b in zip([0.0] + xs, xs)]
    assert min(gaps) > 0.0427 * 1.05
