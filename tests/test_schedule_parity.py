"""Python schedule must match the C firmware exactly."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from launchmonitor.schedule import TimingConfig, compute_schedule

HOST = Path(__file__).resolve().parents[1] / "firmware" / "pico" / "host"


@pytest.fixture(scope="module")
def cli():
    if shutil.which("make") is None or shutil.which("cc") is None:
        pytest.skip("no C toolchain")
    subprocess.run(["make", "-s", "-C", str(HOST), "build/schedule_cli"], check=True)
    return HOST / "build" / "schedule_cli"


@pytest.mark.parametrize("gap_us", [1733, 1857, 2500, 2889, 3939, 6500, 16000, 100, 50000])
def test_matches_c(cli, gap_us):
    t1 = 123_456_789
    c = json.loads(subprocess.run([str(cli), str(t1), str(t1 + gap_us)], capture_output=True, text=True, check=True).stdout)
    p = compute_schedule(TimingConfig(), t1, t1 + gap_us)
    assert c["ok"] == p.ok
    if p.ok:
        assert c["t_impact"] == p.t_impact_us
        assert [tuple(f) for f in c["flashes"]] == p.flashes
        assert c["exposure"] == [p.exposure_start_us, p.exposure_end_us]
