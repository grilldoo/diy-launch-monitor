"""GSPro Open Connect (API v1) client.

GSPro listens on TCP port 921 on the simulator PC and takes one JSON object per
shot. Field names follow the Open Connect v1 spec; verify sign conventions
(HLA, SpinAxis, Path, FaceToTarget) against GSPro's docs on first hookup.
"""

from __future__ import annotations

import json
import socket

from .models import ShotResult

DEFAULT_PORT = 921
DEVICE_ID = "DIY Launch Monitor"


def _r(x: float | None, nd: int = 1) -> float:
    return round(x, nd) if x is not None else 0.0


def shot_message(res: ShotResult, shot_number: int) -> dict:
    has_ball = res.ball_speed_mph is not None
    has_club = res.club_speed_mph is not None or res.face_deg is not None
    msg = {
        "DeviceID": DEVICE_ID,
        "Units": "Yards",
        "ShotNumber": shot_number,
        "APIversion": "1",
        "ShotDataOptions": {
            "ContainsBallData": has_ball,
            "ContainsClubData": has_club,
            "LaunchMonitorIsReady": True,
            "LaunchMonitorBallDetected": True,
            "IsHeartBeat": False,
        },
    }
    if has_ball:
        msg["BallData"] = {
            "Speed": _r(res.ball_speed_mph),
            "SpinAxis": _r(res.spin_axis_deg),
            "TotalSpin": _r(res.total_spin_rpm, 0),
            "BackSpin": _r(res.backspin_rpm, 0),
            "SideSpin": _r(res.sidespin_rpm, 0),
            "HLA": _r(res.hla_deg),
            "VLA": _r(res.vla_deg),
            "CarryDistance": _r(res.carry_yd),
        }
    if has_club:
        msg["ClubData"] = {
            "Speed": _r(res.club_speed_mph),
            "AngleOfAttack": _r(res.attack_deg),
            "FaceToTarget": _r(res.face_deg),
            "Lie": 0.0,
            "Loft": _r(res.loft_deg),
            "Path": _r(res.path_deg),
            "SpeedAtImpact": _r(res.club_speed_mph),
            "VerticalFaceImpact": 0.0,
            "HorizontalFaceImpact": 0.0,
            "ClosureRate": 0.0,
        }
    return msg


def heartbeat_message(ready: bool, ball_detected: bool) -> dict:
    return {
        "DeviceID": DEVICE_ID,
        "Units": "Yards",
        "ShotNumber": 0,
        "APIversion": "1",
        "ShotDataOptions": {
            "ContainsBallData": False,
            "ContainsClubData": False,
            "LaunchMonitorIsReady": ready,
            "LaunchMonitorBallDetected": ball_detected,
            "IsHeartBeat": True,
        },
    }


class GSProClient:
    def __init__(self, host: str, port: int = DEFAULT_PORT, timeout: float = 5.0):
        self.addr = (host, port)
        self.timeout = timeout
        self.sock: socket.socket | None = None
        self.shot_number = 0

    def connect(self) -> None:
        self.sock = socket.create_connection(self.addr, timeout=self.timeout)

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def _send(self, msg: dict) -> dict | None:
        if self.sock is None:
            self.connect()
        self.sock.sendall(json.dumps(msg).encode())
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return None
        try:
            return json.loads(data.decode()) if data else None
        except json.JSONDecodeError:
            return None

    def send_shot(self, res: ShotResult) -> dict | None:
        self.shot_number += 1
        return self._send(shot_message(res, self.shot_number))

    def heartbeat(self, ready: bool = True, ball_detected: bool = True) -> dict | None:
        return self._send(heartbeat_message(ready, ball_detected))
