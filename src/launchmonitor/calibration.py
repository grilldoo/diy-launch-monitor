"""Calibration with a ChArUco board, plus automatic level (IMU) and aim (reference edge).

A ChArUco board is a checkerboard with coded ArUco markers in the white squares, so
every corner has an id: partial views still count, and its orientation can't be misread.

Everything rigid is calibrated once, at build time, and stored relative to the unit
(the "unit frame" is camera A's frame):
  1. intrinsics + lens distortion of each camera   (board waved in front, ~20 poses)
  2. camera B relative to camera A                  (same images)
  3. the unit's reference edge: the direction that points at the target when the edge is
     lined up with the target line                  (board upright, parallel to the edge)
  4. the IMU's orientation relative to the cameras  (the same upright board, with the unit
     tilted on shims a few different ways, IMU read each time)

At every setup, nothing needs the board: the IMU says which way is up, and lining the
reference edge up with the target line gives the aim. UnitCalibration.rig() turns that
into a world-frame Rig (+x target, +y up). `calib reaim` (board upright on the mat) is
still available as a one-off precise aim.

The world origin is camera A, not the ball. The solver only uses directions and
velocities, and the resting ball is located in each shot, so the origin doesn't matter.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from . import geometry as g
from .camera import Camera
from .rig import Rig

MIN_CORNERS = 8
# Upright board facing the unit: board +x (printed left->right) = world +x (target),
# board +y (printed top->bottom) = world -y (down), board +z (into the page) = world -z.
WORLD_FROM_BOARD = np.diag([1.0, -1.0, -1.0])


@dataclass
class Board:
    """ChArUco board. Defaults print at 1:1 on Letter or A4 landscape (260 x 182 mm)."""

    squares_x: int = 10
    squares_y: int = 7
    square_m: float = 0.026
    marker_m: float = 0.019
    dictionary: int = cv2.aruco.DICT_5X5_100
    _cv: object = field(default=None, init=False, repr=False)

    @property
    def cv(self):
        if self._cv is None:
            d = cv2.aruco.getPredefinedDictionary(self.dictionary)
            self._cv = cv2.aruco.CharucoBoard((self.squares_x, self.squares_y), self.square_m, self.marker_m, d)
        return self._cv

    @property
    def size_m(self) -> tuple[float, float]:
        return self.squares_x * self.square_m, self.squares_y * self.square_m

    def corners_3d(self) -> np.ndarray:
        return np.asarray(self.cv.getChessboardCorners(), np.float32)

    def image(self, px_per_mm: float = 10.0) -> np.ndarray:
        w, h = (int(round(s * 1000 * px_per_mm)) for s in self.size_m)
        return self.cv.generateImage((w, h), marginSize=0)


@dataclass
class View:
    ids: np.ndarray  # (N,) corner ids
    uv: np.ndarray  # (N,2) pixel positions


def detect(img: np.ndarray, board: Board) -> View | None:
    corners, ids, _, _ = cv2.aruco.CharucoDetector(board.cv).detectBoard(img)
    if ids is None or len(ids) < MIN_CORNERS:
        return None
    return View(ids.ravel(), corners.reshape(-1, 2))


def calibrate_intrinsics(views: list[View], board: Board, size: tuple[int, int]):
    """Returns (K, dist, rms_px)."""
    P = board.corners_3d()
    obj = [P[v.ids] for v in views]
    img = [v.uv.astype(np.float32).reshape(-1, 1, 2) for v in views]
    rms, K, dist, _, _ = cv2.calibrateCamera(obj, img, size, None, None)
    return K, dist.ravel()[:5], float(rms)


def _common(a: View, b: View):
    ids, ia, ib = np.intersect1d(a.ids, b.ids, return_indices=True)
    return ids, a.uv[ia], b.uv[ib]


def calibrate_stereo(pairs: list[tuple[View, View]], board: Board, KA, dA, KB, dB, size):
    """Pose of camera B relative to A: X_B = R @ X_A + T. Returns (R, T, rms_px)."""
    P = board.corners_3d()
    obj, a, b = [], [], []
    for va, vb in pairs:
        ids, ua, ub = _common(va, vb)
        if len(ids) >= MIN_CORNERS:
            obj.append(P[ids])
            a.append(ua.astype(np.float32).reshape(-1, 1, 2))
            b.append(ub.astype(np.float32).reshape(-1, 1, 2))
    rms, *_, R, T, _, _ = cv2.stereoCalibrate(
        obj, a, b, KA, dA, KB, dB, size, flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9),
    )
    return R, T.ravel(), float(rms)


def board_pose(view: View, board: Board, K, dist) -> np.ndarray:
    """Rotation board -> camera (R_cb) from one view."""
    ok, rvec, _ = cv2.solvePnP(board.corners_3d()[view.ids], view.uv.astype(np.float32), K, dist)
    if not ok:
        raise RuntimeError("solvePnP failed on the board")
    return cv2.Rodrigues(rvec)[0]


def board_axes_in_unit(view: View, board: Board, K, dist) -> tuple[np.ndarray, np.ndarray]:
    """For an upright board facing the unit: (target direction, up) in the unit frame."""
    R_cb = board_pose(view, board, K, dist)
    target = R_cb @ np.array([1.0, 0.0, 0.0])  # printed left -> right
    up = R_cb @ np.array([0.0, -1.0, 0.0])  # printed bottom -> top
    if (R_cb @ np.array([0.0, 0.0, 1.0]))[2] < 0:  # board z points into the page, away from the camera
        raise RuntimeError("board is facing away from the unit: printed side must face the cameras")
    return target, up


def world_from_axes(target_u: np.ndarray, up_u: np.ndarray) -> np.ndarray:
    """R_world_unit (X_w = R @ X_u) from target and up directions given in the unit frame.

    Up is kept exactly; the target direction is projected onto the horizontal plane, so a
    tilted unit still aims along its reference edge's horizontal direction.
    """
    y = up_u / np.linalg.norm(up_u)
    x = target_u - (target_u @ y) * y
    x /= np.linalg.norm(x)
    return np.vstack([x, y, np.cross(x, y)])


def calibrate_imu(ups_unit: list[np.ndarray], accels: list[np.ndarray]) -> tuple[np.ndarray, float]:
    """Rotation IMU -> unit (R_unit_imu) from paired 'up' observations. Returns (R, rms_deg).

    Needs 3+ captures at clearly different tilts (5-10 degrees, in two directions) so the
    rotation is pinned down in all axes. A constant accelerometer offset gets absorbed
    as a small extra rotation, which is accurate over the range of tilts captured.
    """
    A = np.array([a / np.linalg.norm(a) for a in accels])
    B = np.array([u / np.linalg.norm(u) for u in ups_unit])
    R = g.kabsch(A, B)
    err = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", A @ R.T, B), -1, 1)))
    return R, float(np.sqrt(np.mean(err**2)))


@dataclass
class UnitCalibration:
    cams: list[Camera]  # extrinsics relative to the unit frame (camera A's frame)
    ball_cams: list[str]
    club_cams: list[str]
    edge_unit: np.ndarray | None = None  # reference edge -> target, unit frame
    R_unit_imu: np.ndarray | None = None
    R_world_unit_board: np.ndarray | None = None  # board aim (build time, or the last `calib reaim`)
    up_unit_build: np.ndarray | None = None  # "up" when the unit sat level at build time
    meta: dict = field(default_factory=dict)

    def world_from_imu(self, accel: np.ndarray) -> np.ndarray:
        if self.R_unit_imu is None or self.edge_unit is None:
            raise RuntimeError("no IMU / reference-edge calibration: run the build calibration (docs/pi-setup.md)")
        return world_from_axes(self.edge_unit, self.R_unit_imu @ accel)

    def tilt_deg(self, accel: np.ndarray) -> float:
        """How far the unit is tilted compared with how it sat during the build calibration."""
        up = self.R_unit_imu @ accel
        up /= np.linalg.norm(up)
        return float(np.degrees(np.arccos(np.clip(up @ self.up_unit_build, -1, 1))))

    def rig(self, R_world_unit: np.ndarray) -> Rig:
        """World-frame Rig: X_cam = R_cu @ X_unit + t_cu, X_unit = R_wu.T @ X_world."""
        out = {c.name: Camera(c.name, c.K, c.R @ R_world_unit.T, c.t.copy(), c.width, c.height, c.dist)
               for c in self.cams}
        return Rig(ball_cams=[out[n] for n in self.ball_cams], club_cams=[out[n] for n in self.club_cams],
                   meta={**self.meta, "R_world_unit": np.asarray(R_world_unit).tolist()})


def calibrate_from_images(
    pairs: list[tuple[np.ndarray, np.ndarray]],
    edge_pair: tuple[np.ndarray, np.ndarray],
    board: Board,
    names: tuple[str, str] = ("camA", "camB"),
    tilts: list[tuple[np.ndarray, np.ndarray]] | None = None,
) -> tuple[UnitCalibration, dict]:
    """Build-time calibration.

    pairs:     (camA, camB) images of the board in varied poses
    edge_pair: board upright, parallel to the unit's reference edge, TARGET arrow forward
    tilts:     (camA image, accelerometer reading) with the board left exactly where it was for
               edge_pair and the unit tilted on shims; include the untilted position too
    """
    size = (pairs[0][0].shape[1], pairs[0][0].shape[0])
    views = [(detect(a, board), detect(b, board)) for a, b in pairs]
    report: dict = {"pairs_total": len(pairs)}
    intr = {}
    for i, n in enumerate(names):
        vs = [v[i] for v in views if v[i] is not None]
        if len(vs) < 8:
            raise RuntimeError(f"board found in only {len(vs)} images from {n}; need 8+")
        K, d, rms = calibrate_intrinsics(vs, board, size)
        intr[n] = (K, d)
        report[f"{n}_views"] = len(vs)
        report[f"{n}_rms_px"] = round(rms, 3)
    both = [(a, b) for a, b in views if a is not None and b is not None]
    if len(both) < 6:
        raise RuntimeError(f"board seen by both cameras in only {len(both)} pairs; need 6+")
    R, T, rms = calibrate_stereo(both, board, *intr[names[0]], *intr[names[1]], size)
    report["stereo_pairs"] = len(both)
    report["stereo_rms_px"] = round(rms, 3)
    report["baseline_mm"] = round(float(np.linalg.norm(T)) * 1000, 2)

    KA, dA = intr[names[0]]
    KB, dB = intr[names[1]]
    cams = [Camera(names[0], KA, np.eye(3), np.zeros(3), size[0], size[1], np.asarray(dA, float)),
            Camera(names[1], KB, R, T, size[0], size[1], np.asarray(dB, float))]
    cal = UnitCalibration(cams, list(names), list(names), meta={"name": "calibrated 2-camera"})

    edge_view = detect(edge_pair[0], board)
    if edge_view is None:
        raise RuntimeError("reference-edge board not found in camera A's image")
    cal.edge_unit, cal.up_unit_build = board_axes_in_unit(edge_view, board, KA, dA)
    cal.R_world_unit_board = world_from_axes(cal.edge_unit, cal.up_unit_build)

    if tilts:
        ups, accs = [], []
        for img, acc in tilts:
            v = detect(img, board)
            if v is not None:
                ups.append(board_axes_in_unit(v, board, KA, dA)[1])
                accs.append(np.asarray(acc, float))
        if len(ups) < 3:
            raise RuntimeError(f"board found in only {len(ups)} tilt captures; need 3+")
        spread = max(np.degrees(np.arccos(np.clip(a @ b, -1, 1))) for a in ups for b in ups)
        cal.R_unit_imu, report["imu_rms_deg"] = calibrate_imu(ups, accs)
        report["imu_rms_deg"] = round(report["imu_rms_deg"], 3)
        report["imu_tilt_spread_deg"] = round(float(spread), 1)
        if spread < 4:
            report["warning"] = "tilt captures too similar (<4 deg apart): IMU alignment is poorly constrained"
    return cal, report


def reaim(cal: UnitCalibration, aim_img_a: np.ndarray, board: Board) -> UnitCalibration:
    """One-off precise aim: board upright on the mat facing the unit, TARGET arrow at the target."""
    a = next(c for c in cal.cams if c.name == cal.ball_cams[0])
    view = detect(aim_img_a, board)
    if view is None:
        raise RuntimeError("aim board not found in camera A's image")
    out = UnitCalibration(**{**cal.__dict__})
    out.R_world_unit_board = world_from_axes(*board_axes_in_unit(view, board, a.K, a.dist))
    return out


def _arr(x):
    return None if x is None else np.asarray(x, float)


def save_calibration(cal: UnitCalibration, path: str | Path, extra: dict | None = None) -> None:
    data = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "frame": "unit (camera A)",
        "cameras": [
            {"name": c.name, "K": c.K.tolist(), "dist": np.asarray(c.dist).tolist(), "R": c.R.tolist(),
             "t": c.t.tolist(), "width": c.width, "height": c.height}
            for c in cal.cams
        ],
        "ball_cams": cal.ball_cams,
        "club_cams": cal.club_cams,
        "edge_unit": None if cal.edge_unit is None else cal.edge_unit.tolist(),
        "R_unit_imu": None if cal.R_unit_imu is None else cal.R_unit_imu.tolist(),
        "R_world_unit_board": None if cal.R_world_unit_board is None else cal.R_world_unit_board.tolist(),
        "up_unit_build": None if cal.up_unit_build is None else cal.up_unit_build.tolist(),
        "meta": {**cal.meta, **(extra or {})},
    }
    Path(path).write_text(json.dumps(data, indent=1) + "\n")


def load_calibration(path: str | Path) -> UnitCalibration:
    data = json.loads(Path(path).read_text())
    cams = [Camera(c["name"], np.array(c["K"]), np.array(c["R"]), np.array(c["t"]), c["width"], c["height"],
                   np.array(c["dist"])) for c in data["cameras"]]
    return UnitCalibration(cams, data["ball_cams"], data["club_cams"], _arr(data.get("edge_unit")),
                           _arr(data.get("R_unit_imu")), _arr(data.get("R_world_unit_board")),
                           _arr(data.get("up_unit_build")), data.get("meta", {}))


def board_print_image(board: Board, dpi: int = 300) -> np.ndarray:
    """Printable page image (Letter/A4 landscape, 1:1 at `dpi`) with orientation labels."""
    px_mm = dpi / 25.4
    page = np.full((int(round(210 * px_mm)), int(round(279 * px_mm))), 255, np.uint8)
    b = board.image(px_mm)
    y0 = int(round(11 * px_mm))
    x0 = (page.shape[1] - b.shape[1]) // 2
    page[y0 : y0 + b.shape[0], x0 : x0 + b.shape[1]] = b
    font, s = cv2.FONT_HERSHEY_SIMPLEX, 0.08 * px_mm
    cv2.putText(page, "TOP - this edge up, printed side facing the launch monitor", (x0, int(8 * px_mm)), font, s * 0.9, 0, 2)
    w_mm, h_mm = (v * 1000 for v in board.size_m)
    yb = y0 + b.shape[0] + int(9 * px_mm)
    cv2.putText(page, "TARGET  ------->", (x0 + b.shape[1] - int(95 * px_mm), yb), font, s * 1.8, 0, 6)
    cv2.putText(page, f"squares {board.square_m * 1000:.0f} mm, markers {board.marker_m * 1000:.0f} mm, board {w_mm:.0f} x "
                f"{h_mm:.0f} mm: print at 100%, measure", (x0, yb), font, s * 0.6, 0, 2)
    return page
