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
