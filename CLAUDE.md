# Notes for Claude Code sessions

The owner builds and solders the hardware. Claude Code writes the software. Most sessions
run in the cloud with **no hardware attached**, so all logic must be testable through the
simulator (`src/launchmonitor/sim.py`) or with recorded shot data.

## Commands
- `pytest`: full Python suite. It also builds `firmware/pico/host/build/schedule_cli` and checks it matches `schedule.py`
- `make -C firmware/pico/host test`: C unit tests
- `python tools/accuracy_study.py`: regenerate the accuracy table in docs/design.md when the solver or rig changes

## Conventions
- World frame: origin at ball centre, +x target, +y up, +z away from a right-handed golfer. Sign conventions are in docs/design.md; keep the solver, sim and GSPro output consistent with them.
- SI units internally; convert to mph / rpm / yd / degrees only in results.
- `firmware/pico/src/lm_timing.c` and `src/launchmonitor/schedule.py` are mirrors. Change both in the same commit; the parity test enforces it.
- Firmware timing logic stays SDK-free in `lm_timing.c` so it is host-testable; `main.c` is only glue.
- New solver features get a simulator-driven test with known ground truth. Tolerances come from accuracy_study (~4 sigma), not guesses.
- Anything not yet verified on hardware is marked UNTESTED / UNVERIFIED in comments or docs. Don't remove those marks without a bench result.
