"""Stereo calibration with a ChArUco board -> a calibrated Rig saved as JSON.

A ChArUco board is a checkerboard with coded ArUco markers in the white squares, so
every corner has an id. That means partial views still count, and the board's
orientation can never come out flipped.

  1. Intrinsics: each camera sees the board in ~15-25 varied poses -> K + lens distortion.
  2. Stereo: the same poses, seen by both cameras at once -> pose of camera B relative to A.
  3. World frame ("aim"): the board stands upright on the mat, printed side facing the
     unit, its "TARGET ->" arrow pointing at the target. That gives +x (target) and
     +y (up), so the stand must be vertical: check it with a level. One image pair is enough.

Steps 1-2 are done once at build time (the rigid extrusion keeps them). Step 3 is
repeated whenever the unit is moved. The world origin ends up at the board's corner,
not the ball. That doesn't matter: the solver only uses directions and velocities,
and the resting ball is located in each shot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .camera import Camera
from .rig import Rig

MIN_CORNERS = 8
# Upright board seen from the unit: board +x (printed left->right) = world +x,
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


def world_pose(view: View, board: Board, K, dist) -> tuple[np.ndarray, np.ndarray]:
    """Camera extrinsics (R, t: world -> camera) from one image of the upright aim board."""
    ok, rvec, tvec = cv2.solvePnP(board.corners_3d()[view.ids], view.uv.astype(np.float32), K, dist)
    if not ok:
        raise RuntimeError("solvePnP failed on the aim board")
    R_cb, _ = cv2.Rodrigues(rvec)
    t_cb = tvec.ravel()
    R = R_cb @ WORLD_FROM_BOARD.T
    cam_world = -R.T @ t_cb
    if cam_world[2] <= 0:
        raise RuntimeError("aim board is facing away from the unit: printed side must face the cameras")
    return R, t_cb


def build_rig(names, intrinsics, stereo_R, stereo_T, aim_view_a: View, board: Board, size) -> Rig:
    a, b = names
    KA, dA = intrinsics[a]
    KB, dB = intrinsics[b]
    RA, tA = world_pose(aim_view_a, board, KA, dA)
    RB, tB = stereo_R @ RA, stereo_R @ tA + stereo_T
    cams = [
        Camera(a, KA, RA, tA, size[0], size[1], np.asarray(dA, float)),
        Camera(b, KB, RB, tB, size[0], size[1], np.asarray(dB, float)),
    ]
    return Rig(ball_cams=cams, club_cams=cams, meta={"name": "calibrated 2-camera"})


def calibrate_from_images(
    pairs: list[tuple[np.ndarray, np.ndarray]],
    aim_pair: tuple[np.ndarray, np.ndarray],
    board: Board,
    names: tuple[str, str] = ("camA", "camB"),
) -> tuple[Rig, dict]:
    """Full calibration from image pairs (camA, camB). Returns (rig, report)."""
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
    aim = detect(aim_pair[0], board)
    if aim is None:
        raise RuntimeError("aim board not found in camera A's image")
    return build_rig(names, intr, R, T, aim, board, size), report


def reaim(rig: Rig, aim_img_a: np.ndarray, board: Board) -> Rig:
    """New world frame from a fresh aim-board image, keeping intrinsics and stereo (unit moved)."""
    a, b = rig.ball_cams[:2]
    view = detect(aim_img_a, board)
    if view is None:
        raise RuntimeError("aim board not found in camera A's image")
    RA, tA = world_pose(view, board, a.K, a.dist)
    # B relative to A is unchanged: X_B = R_ab X_A + T_ab
    R_ab = b.R @ a.R.T
    T_ab = b.t - R_ab @ a.t
    cams = [Camera(a.name, a.K, RA, tA, a.width, a.height, a.dist),
            Camera(b.name, b.K, R_ab @ RA, R_ab @ tA + T_ab, b.width, b.height, b.dist)]
    return Rig(ball_cams=cams, club_cams=cams, meta=dict(rig.meta))


def save_rig(rig: Rig, path: str | Path, extra: dict | None = None) -> None:
    data = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cameras": [
            {"name": c.name, "K": c.K.tolist(), "dist": np.asarray(c.dist).tolist(), "R": c.R.tolist(),
             "t": c.t.tolist(), "width": c.width, "height": c.height}
            for c in rig.cameras
        ],
        "ball_cams": [c.name for c in rig.ball_cams],
        "club_cams": [c.name for c in rig.club_cams],
        "meta": {**rig.meta, **(extra or {})},
    }
    Path(path).write_text(json.dumps(data, indent=1) + "\n")


def load_rig(path: str | Path) -> Rig:
    data = json.loads(Path(path).read_text())
    cams = {
        c["name"]: Camera(c["name"], np.array(c["K"]), np.array(c["R"]), np.array(c["t"]), c["width"], c["height"],
                          np.array(c["dist"]))
        for c in data["cameras"]
    }
    return Rig(
        ball_cams=[cams[n] for n in data["ball_cams"]],
        club_cams=[cams[n] for n in data["club_cams"]],
        meta=data.get("meta", {}),
    )


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
