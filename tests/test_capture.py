import ctypes
import json

import numpy as np

from launchmonitor import imx296
from launchmonitor.capture import FramePairer, libcamera_config_yaml


def test_pairer_matches_by_timestamp():
    p = FramePairer(["camA", "camB"], tolerance_ns=5_000_000)
    f = np.zeros((2, 2))
    assert p.add("camA", 1_000_000_000, f) is None
    got = p.add("camB", 1_001_000_000, f + 1)
    assert set(got) == {"camA", "camB"} and got["camB"][0, 0] == 1


def test_pairer_drops_orphan_frame():
    p = FramePairer(["camA", "camB"], tolerance_ns=5_000_000)
    f = np.zeros((1, 1))
    p.add("camA", 1_000_000_000, f)  # camB missed this trigger
    assert p.add("camB", 3_000_000_000, f) is None  # next shot, 2 s later
    got = p.add("camA", 3_000_500_000, f + 7)
    assert got is not None and got["camA"][0, 0] == 7


def test_libcamera_yaml_is_valid_json_with_timeout():
    cfg = json.loads(libcamera_config_yaml(1234))  # libcamera's YAML here is plain JSON
    assert cfg["target"] == "pisp" and cfg["pipeline_handler"]["camera_timeout_value_ms"] == 1234


def test_trigger_register_writes():
    sent = []

    def fake_ioctl(fd, req, data):
        assert req == imx296.I2C_RDWR and data.nmsgs == 1
        m = data.msgs[0]
        buf = (ctypes.c_uint8 * m.len).from_address(m.buf)
        sent.append((m.addr, bytes(buf)))

    imx296.Sensor(4, ioctl=fake_ioctl).set_trigger(True)
    assert sent[0] == (0x1A, bytes([0x30, 0x0A, 0x01]))
    assert (0x1A, bytes([0x30, 0xAE, 0x01])) in sent
    assert sent[-1] == (0x1A, bytes([0x30, 0x0A, 0x00]))
