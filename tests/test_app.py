"""Whole loop off-hardware: simulated Pico + cameras -> pipeline -> fake GSPro server."""

import json
import socket
import threading

import numpy as np
import pytest

from launchmonitor.app import LaunchMonitor
from launchmonitor.gspro import GSProClient
from launchmonitor.models import MPS_TO_MPH
from launchmonitor.pipeline import load_shot, process_shot
from launchmonitor.rig import two_camera_rig
from launchmonitor.sim_source import SimulatedLaunchMonitor


class FakeGSPro:
    def __init__(self):
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(1)
        self.port = self.srv.getsockname()[1]
        self.messages = []
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        conn, _ = self.srv.accept()
        while data := conn.recv(65536):
            self.messages.append(json.loads(data.decode()))
            conn.sendall(b'{"Code":200,"Message":"Shot received successfully"}')


@pytest.mark.parametrize("distorted", [False, True], ids=["pinhole", "lens-distortion"])
def test_loop_sends_accurate_shots_to_gspro(tmp_path, distorted):
    rig = two_camera_rig()
    if distorted:
        for c in rig.cameras:
            c.dist = np.array([-0.12, 0.05, 0.0005, -0.0003, 0.0])
    sim = SimulatedLaunchMonitor(rig, seed=3)
    gs = FakeGSPro()
    lm = LaunchMonitor(rig, sim, sim, GSProClient("127.0.0.1", gs.port), tmp_path, log=lambda s: None)
    for _ in range(2):
        r = lm.step()
        t = sim.last_truth
        assert r is not None
        assert r.ball_speed_mph == pytest.approx(t.ball_speed_mps * MPS_TO_MPH, abs=0.6)
        assert r.vla_deg == pytest.approx(t.vla_deg, abs=0.3)
        assert r.total_spin_rpm == pytest.approx(np.hypot(t.backspin_rpm, t.sidespin_rpm), rel=0.04)
    for _ in range(50):
        if len(gs.messages) == 2:
            break
        threading.Event().wait(0.05)
    assert [m["ShotNumber"] for m in gs.messages] == [1, 2]
    assert gs.messages[1]["BallData"]["Speed"] == round(r.ball_speed_mph, 1)

    # Saved shots replay to the same answer.
    d = sorted(tmp_path.iterdir())[-1]
    frames, pico, _ = load_shot(d)
    _, again = process_shot(frames, pico, rig)
    assert again.ball_speed_mph == pytest.approx(r.ball_speed_mph, abs=1e-6)


def test_gspro_down_does_not_crash(tmp_path):
    rig = two_camera_rig()
    sim = SimulatedLaunchMonitor(rig, seed=1)
    logs = []
    lm = LaunchMonitor(rig, sim, sim, GSProClient("127.0.0.1", 1, timeout=0.5), None, log=logs.append)
    assert lm.step() is not None
    assert any("GSPro" in s for s in logs)
