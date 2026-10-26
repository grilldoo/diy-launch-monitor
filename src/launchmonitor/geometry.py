"""Direction, rotation and spin-frame helpers shared by the simulator and solver."""

from __future__ import annotations

import numpy as np

Y_UP = np.array([0.0, 1.0, 0.0])
Z_RIGHT = np.array([0.0, 0.0, 1.0])


def direction(horizontal_deg: float, vertical_deg: float) -> np.ndarray:
    """Unit vector from a horizontal angle (+ right / +z) and vertical angle (+ up)."""
    h, v = np.radians(horizontal_deg), np.radians(vertical_deg)
    return np.array([np.cos(v) * np.cos(h), np.sin(v), np.cos(v) * np.sin(h)])


def angles(vec: np.ndarray) -> tuple[float, float]:
    """Inverse of direction(): returns (horizontal_deg, vertical_deg)."""
    x, y, z = vec
    return float(np.degrees(np.arctan2(z, x))), float(np.degrees(np.arctan2(y, np.hypot(x, z))))


def spin_frame(launch_dir: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Axes for decomposing spin: backspin is about `right`, curve-right sidespin about `-up`."""
    right = np.cross(launch_dir, Y_UP)
    right /= np.linalg.norm(right)
    up = np.cross(right, launch_dir)
    return right, up


def rotvec_to_matrix(w: np.ndarray) -> np.ndarray:
    theta = np.linalg.norm(w)
    if theta < 1e-12:
        return np.eye(3)
    k = w / theta
    Kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + np.sin(theta) * Kx + (1 - np.cos(theta)) * Kx @ Kx


def matrix_to_rotvec(R: np.ndarray) -> np.ndarray:
    cos_t = np.clip((np.trace(R) - 1) / 2, -1.0, 1.0)
    theta = np.arccos(cos_t)
    if theta < 1e-9:
        return np.zeros(3)
    axis = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * np.sin(theta))
    return axis * theta


def kabsch(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Rotation R minimising |R A_i - B_i| for centred point sets A, B (N,3)."""
    H = A.T @ B
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    return Vt.T @ np.diag([1.0, 1.0, d]) @ U.T


def fit_line(times: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Least-squares p(t) = p0 + v t. Returns (p0, v)."""
    A = np.column_stack([np.ones_like(times), times])
    coef, *_ = np.linalg.lstsq(A, points, rcond=None)
    return coef[0], coef[1]
