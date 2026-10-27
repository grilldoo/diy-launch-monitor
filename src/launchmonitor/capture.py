"""Frame capture: one synchronized multi-exposure frame per camera, per shot.

  * PiCameraSource: real cameras via picamera2 (on the Pi; picamera2 comes from apt)
  * FramePairer: matches frames from different cameras by sensor timestamp
  * SimulatedLaunchMonitor (sim_source.py) stands in for cameras + Pico off-hardware

In trigger mode a camera only produces a frame when the Pico pulses its trigger
line, so "the next frame from every camera, with timestamps that agree" is the shot.
"""

from __future__ import annotations

import os
import queue
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import imx296

# Frames from one trigger pulse arrive within a few ms of each other.
PAIR_TOLERANCE_NS = 5_000_000
# In trigger mode libcamera waits indefinitely for frames between shots instead of erroring.
LIBCAMERA_TIMEOUT_MS = 3_600_000


def libcamera_config_yaml(timeout_ms: int = LIBCAMERA_TIMEOUT_MS) -> str:
    """Pi 5 (PiSP) pipeline-handler config with a long frame timeout (InnoMaker manual 4.4).

    UNVERIFIED: key layout follows /usr/share/libcamera/pipeline/rpi/pisp/example.yaml.
    """
    return (
        '{\n    "version": 1.0,\n    "target": "pisp",\n    "pipeline_handler":\n    {\n'
        f'        "camera_timeout_value_ms": {int(timeout_ms)}\n    }}\n}}\n'
    )


def install_libcamera_timeout(timeout_ms: int = LIBCAMERA_TIMEOUT_MS) -> Path:
    """Write the config and point libcamera at it. Must run before picamera2 is imported."""
    path = Path(tempfile.gettempdir()) / "launchmonitor-libcamera.yaml"
    path.write_text(libcamera_config_yaml(timeout_ms))
    os.environ["LIBCAMERA_RPI_CONFIG_FILE"] = str(path)
    return path


@dataclass
class FramePairer:
    """Collects (camera, timestamp, frame) arrivals and emits complete, time-aligned sets."""

    cameras: list[str]
    tolerance_ns: int = PAIR_TOLERANCE_NS
    _pending: dict[str, list[tuple[int, np.ndarray]]] = field(default_factory=dict)

    def add(self, cam: str, ts_ns: int, frame: np.ndarray) -> dict[str, np.ndarray] | None:
        self._pending.setdefault(cam, []).append((ts_ns, frame))
        if any(not self._pending.get(c) for c in self.cameras):
            return None
        ref = max(self._pending[c][0][0] for c in self.cameras)
        # Drop frames that are too old to match the newest head (e.g. a missed trigger on one camera).
        for c in self.cameras:
            self._pending[c] = [(t, f) for t, f in self._pending[c] if t >= ref - self.tolerance_ns]
        if any(not self._pending.get(c) for c in self.cameras):
            return None
        heads = {c: self._pending[c][0] for c in self.cameras}
        ts = [t for t, _ in heads.values()]
        if max(ts) - min(ts) > self.tolerance_ns:
            return None
        for c in self.cameras:
            self._pending[c].pop(0)
        return {c: f for c, (_, f) in heads.items()}


class PiCameraSource:
    """Two (or more) InnoMaker IMX296 cameras on one Pi 5, in external-trigger mode.

    UNTESTED ON HARDWARE. Each camera runs a thread that blocks on capture_request();
    frames go through a FramePairer. Exposure is fixed (no auto-exposure) and long
    enough to cover the whole flash burst, in case the sensor uses the register exposure
    rather than the trigger pulse width.
    """

    def __init__(self, names: dict[int, str], exposure_us: int = 8000, gain: float = 2.0, trigger: bool = True):
        install_libcamera_timeout()
        from picamera2 import Picamera2  # noqa: PLC0415  (Pi-only; from apt: python3-picamera2)

        self.names = names
        self.trigger = trigger
        self.cams = {}
        self.q: queue.Queue = queue.Queue()
        self.pairer = FramePairer(list(names.values()))
        self._stop = threading.Event()
        for num, name in names.items():
            cam = Picamera2(num)
            cfg = cam.create_still_configuration(
                main={"size": (1456, 1088), "format": "YUV420"},
                buffer_count=3,
                controls={"AeEnable": False, "ExposureTime": exposure_us, "AnalogueGain": gain},
            )
            cam.configure(cfg)
            self.cams[name] = (num, cam)

    def start(self) -> None:
        for name, (num, cam) in self.cams.items():
            cam.start()
            if self.trigger:
                with imx296.Sensor(imx296.PI5_BUS[num]) as s:
                    s.set_trigger(True)
            threading.Thread(target=self._reader, args=(name, cam), daemon=True).start()

    def _reader(self, name: str, cam) -> None:
        while not self._stop.is_set():
            req = cam.capture_request()
            try:
                frame = req.make_array("main")[:1088]  # Y plane of YUV420 = the mono image
                ts = int(req.get_metadata().get("SensorTimestamp", time.monotonic_ns()))
            finally:
                req.release()
            self.q.put((name, ts, frame.copy()))

    def collect(self, timeout: float = 1.0) -> dict[str, np.ndarray] | None:
        """Next time-aligned set of frames, or None if none arrives within `timeout`."""
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            try:
                name, ts, frame = self.q.get(timeout=left)
            except queue.Empty:
                return None
            got = self.pairer.add(name, ts, frame)
            if got is not None:
                return got
        return None

    def stop(self) -> None:
        self._stop.set()
        for num, cam in self.cams.values():
            if self.trigger:
                try:
                    with imx296.Sensor(imx296.PI5_BUS[num]) as s:
                        s.set_trigger(False)
                except OSError:
                    pass
            cam.stop()
