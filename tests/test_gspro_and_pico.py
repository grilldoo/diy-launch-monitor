import json

from launchmonitor.gspro import shot_message
from launchmonitor.models import ShotResult
from launchmonitor.pico_link import PicoShot, parse_line


def test_gspro_message_shape():
    r = ShotResult(ball_speed_mph=150.2, vla_deg=12.1, hla_deg=-1.2, total_spin_rpm=2800, backspin_rpm=2750,
                   sidespin_rpm=-500, spin_axis_deg=-10.3, club_speed_mph=103.4, face_deg=-0.5, path_deg=1.5)
    m = json.loads(json.dumps(shot_message(r, 7)))
    assert m["ShotNumber"] == 7 and m["APIversion"] == "1"
    assert m["BallData"]["Speed"] == 150.2 and m["BallData"]["SpinAxis"] == -10.3
    assert m["ClubData"]["Path"] == 1.5 and m["ShotDataOptions"]["ContainsClubData"]


def test_parse_pico_shot():
    s = parse_line('{"type":"shot","club_speed":45.2,"t_impact":1,"flashes":[[-2000,0],[983,1]],"exposure":[-2050,1048]}')
    assert isinstance(s, PicoShot)
    assert s.flash_kinds == [0, 1] and abs(s.flash_times_s[1] - 983e-6) < 1e-12
    assert parse_line("debug text") is None
    assert parse_line('{"type":"pong"}') == {"type": "pong"}
