import numpy as np

from launchmonitor.detect import detect_balls
from launchmonitor.models import ShotTruth
from launchmonitor.rig import two_camera_rig
from launchmonitor.schedule import FLASH_BALL
from launchmonitor.sim import render, shot_state


def test_detects_every_ball_image():
    rig = two_camera_rig()
    st = shot_state(ShotTruth(65, 12, 1, 3000, 0, 47, 0, -2, 0, 13))
    for cam in rig.ball_cams:
        img = render(st, cam)
        blobs = detect_balls(img)
        truth = [cam.project(st.ball_centers[i][None])[0][0] for i, k in enumerate(st.flash_kinds) if k == FLASH_BALL]
        truth.append(cam.project(np.zeros((1, 3)))[0][0])  # resting ball
        assert len(blobs) == len(truth)
        for t in truth:
            err = min(np.hypot(b.u - t[0], b.v - t[1]) for b in blobs)
            assert err < 1.5
        # Resting ball is lit by every club flash, so it is the brightest blob.
        rest = max(blobs, key=lambda b: b.brightness)
        assert np.hypot(rest.u - truth[-1][0], rest.v - truth[-1][1]) < 1.5
