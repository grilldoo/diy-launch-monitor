"""Pinhole camera model and N-view triangulation.

World frame (see docs/design.md): origin at the ball centre at address,
+x toward the target, +y up, +z away from a right-handed golfer (toward the unit).
Camera frame follows OpenCV: +x right, +y down, +z forward.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Camera:
    name: str
    K: np.ndarray  # 3x3 intrinsics
    R: np.ndarray  # 3x3 world -> camera rotation
    t: np.ndarray  # (3,) world -> camera translation
    width: int
    height: int

    @property
    def P(self) -> np.ndarray:
        return self.K @ np.hstack([self.R, self.t[:, None]])

    @property
    def center(self) -> np.ndarray:
        return -self.R.T @ self.t

    def project(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Project world points (N,3) -> pixels (N,2) and depth (N,)."""
        X = np.atleast_2d(X)
        Xc = X @ self.R.T + self.t
        uvw = Xc @ self.K.T
        return uvw[:, :2] / uvw[:, 2:3], Xc[:, 2]

    def in_image(self, uv: np.ndarray, depth: np.ndarray, margin: float = 2.0) -> np.ndarray:
        uv = np.atleast_2d(uv)
        return (
            (depth > 0)
            & (uv[:, 0] >= margin)
            & (uv[:, 0] < self.width - margin)
            & (uv[:, 1] >= margin)
            & (uv[:, 1] < self.height - margin)
        )


def look_at(
    name: str,
    eye,
    target,
    focal_mm: float,
    pixel_um: float = 3.45,
    width: int = 1456,
    height: int = 1088,
    up=(0.0, 1.0, 0.0),
) -> Camera:
    """Build a camera at `eye` looking at `target`. Defaults match the Pi Global Shutter camera (IMX296)."""
    eye = np.asarray(eye, float)
    fwd = np.asarray(target, float) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.asarray(up, float))
    right /= np.linalg.norm(right)
    down = np.cross(fwd, right)
    R = np.vstack([right, down, fwd])
    f_px = focal_mm / (pixel_um * 1e-3)
    K = np.array([[f_px, 0, width / 2], [0, f_px, height / 2], [0, 0, 1.0]])
    return Camera(name, K, R, -R @ eye, width, height)


def triangulate(cams: list[Camera], uvs: list[np.ndarray]) -> np.ndarray:
    """Linear (DLT) triangulation of one point seen by two or more cameras."""
    if len(cams) < 2:
        raise ValueError("need at least two views")
    rows = []
    for cam, (u, v) in zip(cams, uvs):
        P = cam.P
        rows.append(u * P[2] - P[0])
        rows.append(v * P[2] - P[1])
    A = np.asarray(rows)
    A /= np.linalg.norm(A, axis=1, keepdims=True)  # equal weight per observation
    _, _, Vt = np.linalg.svd(A)
    X = Vt[-1]
    return X[:3] / X[3]
