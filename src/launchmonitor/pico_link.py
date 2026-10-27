"""Parse the JSON lines the Pico timing controller prints over USB serial.

Shot line, times in microseconds relative to predicted impact:
  {"type":"shot","club_speed":45.21,"t_impact":123456789,
   "flashes":[[-1991,0],[-1106,0],[-332,0],[983,1],...],"exposure":[-2041,4997]}
Other lines: {"type":"ready"}, {"type":"pong"}, {"type":"error","msg":"..."}.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass
class PicoShot:
    club_speed_mps: float
    flash_times_s: list[float]
    flash_kinds: list[int]
    exposure_s: tuple[float, float]


def parse_line(line: str) -> PicoShot | dict | None:
    line = line.strip()
    if not line.startswith("{"):
        return None  # firmware debug output
    msg = json.loads(line)
    if msg.get("type") != "shot":
        return msg
    return PicoShot(
        club_speed_mps=float(msg["club_speed"]),
        flash_times_s=[t * 1e-6 for t, _ in msg["flashes"]],
        flash_kinds=[int(k) for _, k in msg["flashes"]],
        exposure_s=(msg["exposure"][0] * 1e-6, msg["exposure"][1] * 1e-6),
    )


class PicoSerial:
    """The Pico timing controller over USB serial (pyserial; `pip install -e '.[pi]'`)."""

    def __init__(self, port: str = "/dev/ttyACM0", baud: int = 115200):
        import serial  # noqa: PLC0415

        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.last_message: dict | None = None

    def send(self, command: str) -> None:
        self.ser.write((command.strip() + "\n").encode())

    def read_shot(self, timeout: float = 1.0) -> PicoShot | None:
        """Next shot report, or None on timeout. Other messages are kept in last_message."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            try:
                msg = parse_line(raw.decode(errors="replace"))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if isinstance(msg, PicoShot):
                return msg
            if msg is not None:
                self.last_message = msg
        return None

    def close(self) -> None:
        self.ser.close()
