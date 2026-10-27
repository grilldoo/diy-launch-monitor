"""The launch monitor main loop: Pico report -> frames -> result -> GSPro (+ saved shot)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from .gspro import GSProClient
from .models import ShotResult
from .pipeline import process_shot, save_shot
from .rig import Rig

HEARTBEAT_S = 5.0


def format_result(r: ShotResult) -> str:
    def f(v, fmt):
        return "-" if v is None else format(v, fmt)

    s = (f"ball {f(r.ball_speed_mph, '.1f')} mph  VLA {f(r.vla_deg, '.1f')}  HLA {f(r.hla_deg, '+.1f')}  "
         f"spin {f(r.total_spin_rpm, '.0f')} rpm  axis {f(r.spin_axis_deg, '+.1f')}  carry {f(r.carry_yd, '.0f')} yd")
    if r.club_speed_mph is not None or r.face_deg is not None:
        s += (f"\nclub {f(r.club_speed_mph, '.1f')} mph  path {f(r.path_deg, '+.1f')}  face {f(r.face_deg, '+.1f')}  "
              f"attack {f(r.attack_deg, '+.1f')}  loft {f(r.loft_deg, '.1f')}")
    if r.warnings:
        s += "\n  (" + "; ".join(r.warnings) + ")"
    return s


class LaunchMonitor:
    """`pico` needs read_shot(timeout); `frames` needs collect(timeout). See pico_link, capture, sim_source.

    `rig` is a Rig, or a function returning one. A function is re-evaluated while idle
    (every HEARTBEAT_S), which is how the IMU's level correction follows a bumped unit.
    """

    def __init__(self, rig: Rig | Callable[[], Rig], pico, frames, gspro: GSProClient | None = None,
                 shots_dir: str | Path | None = None, log: Callable[[str], None] = print):
        self._rig_fn = rig if callable(rig) else None
        self.rig = rig() if callable(rig) else rig
        self.pico = pico
        self.frames = frames
        self.gspro = gspro
        self.shots_dir = Path(shots_dir) if shots_dir else None
        self.log = log
        self._last_heartbeat = 0.0

    def _gspro_call(self, fn, *args):
        if self.gspro is None:
            return None
        try:
            return fn(*args)
        except OSError as e:  # GSPro closed or not running: drop the socket, retry next time
            self.log(f"GSPro: {e}")
            self.gspro.close()
            return None

    def step(self, timeout: float = 1.0) -> ShotResult | None:
        shot = self.pico.read_shot(timeout)
        if shot is None:
            if time.monotonic() - self._last_heartbeat > HEARTBEAT_S:
                self._last_heartbeat = time.monotonic()
                if self._rig_fn is not None:
                    self.rig = self._rig_fn()
                self._gspro_call(self.gspro.heartbeat if self.gspro else None)
            return None
        frames = self.frames.collect(timeout=1.0)
        if not frames:
            self.log("shot triggered but no camera frames arrived")
            return None
        t0 = time.monotonic()
        try:
            _, result = process_shot(frames, shot, self.rig)
        except Exception as e:  # never lose a shot to a solver bug: save the frames for replay
            result = None
            self.log(f"processing failed: {e!r}")
        if self.shots_dir:
            extra = {"processing_s": round(time.monotonic() - t0, 3)}
            if "R_world_unit" in self.rig.meta:  # level + aim used, so replays reproduce this shot exactly
                extra["R_world_unit"] = self.rig.meta["R_world_unit"]
            d = save_shot(self.shots_dir, frames, shot, result, extra)
            self.log(f"saved {d}")
        if result is None:
            return None
        self.log(format_result(result))
        if result.ball_speed_mph is not None:
            reply = self._gspro_call(self.gspro.send_shot if self.gspro else None, result)
            if reply is not None and reply.get("Code") not in (200, 201):
                self.log(f"GSPro replied: {reply}")
        return result

    def run(self, max_shots: int | None = None) -> None:
        n = 0
        while max_shots is None or n < max_shots:
            if self.step() is not None:
                n += 1
