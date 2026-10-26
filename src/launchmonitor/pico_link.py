"""Parse the JSON lines the Pico timing controller prints over USB serial.

Shot line, times in microseconds relative to predicted impact:
  {"type":"shot","club_speed":45.21,"t_impact":123456789,
   "flashes":[[-1991,0],[-1106,0],[-332,0],[983,1],...],"exposure":[-2041,4997]}
Other lines: {"type":"ready"}, {"type":"pong"}, {"type":"error","msg":"..."}.
"""

from __future__ import annotations

import json
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
