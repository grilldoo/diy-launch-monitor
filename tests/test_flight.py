import pytest

from launchmonitor.flight import simulate_flight
from launchmonitor.models import M_TO_YD, MPS_TO_MPH

# PGA Tour averages (TrackMan): ball mph, launch deg, spin rpm, carry yd
TOUR = [(167, 10.9, 2686, 275), (120, 16.3, 7097, 172), (102, 24.2, 9304, 136)]


@pytest.mark.parametrize("mph,vla,rpm,carry", TOUR)
def test_carry_near_tour_average(mph, vla, rpm, carry):
    p = simulate_flight(mph / MPS_TO_MPH, vla, 0, rpm, 0)
    assert p[-1, 0] * M_TO_YD == pytest.approx(carry, rel=0.05)


def test_slice_spin_curves_right():
    p = simulate_flight(60, 12, 0, 3000, 800)
    assert p[-1, 2] > 5
