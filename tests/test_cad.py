"""Printed parts must match the geometry the solver assumes."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_cad", ROOT / "tools" / "export_cad.py")
export_cad = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_cad)


def test_generated_scad_is_up_to_date(tmp_path):
    export_cad.write_ball_pattern(tmp_path)
    export_cad.write_rig_angles(tmp_path)
    for name in ("ball_pattern.scad", "rig_angles.scad"):
        committed = (ROOT / "cad" / "generated" / name).read_text()
        assert (tmp_path / name).read_text() == committed, f"run tools/export_cad.py ({name} is stale)"


def test_printed_club_sticker_is_not_mirrored():
    """The sheet must look like the face seen from the front (toe on the left for a
    right-handed club). A mirrored print can't be fixed by rotating the sticker."""
    import re

    import numpy as np

    from launchmonitor.camera import look_at
    from launchmonitor.markers import FACE_MARKERS_UV

    svg = (ROOT / "cad" / "club_markers.svg").read_text()
    printed = np.array([(float(a), float(b)) for a, b in re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', svg)][:5])
    cam = look_at("front", [0.6, 0.0, 0.0], [0.0, 0.0, 0.0], 8.0)  # in front of the face, looking back at it
    toe, up = np.array([0.0, 0.0, 1.0]), np.array([0.0, 1.0, 0.0])
    seen = cam.project(np.array([u * toe + v * up for u, v in FACE_MARKERS_UV]))[0]
    A = np.column_stack([printed, np.ones(5)])
    coef, *_ = np.linalg.lstsq(A, seen, rcond=None)
    assert np.linalg.det(coef[:2, :2]) > 0
    assert np.allclose(A @ coef, seen, atol=1e-6)
