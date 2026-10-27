"""Command line: python -m launchmonitor <command> ...

  run            the launch monitor (real hardware, or --sim)
  replay DIR..   re-process saved shots
  calib board    write the printable ChArUco board
  calib capture  save board image pairs from both cameras (free-running)
  calib solve    compute calibration.json from captured pairs
  calib reaim    optional precise aim from the board (use with run --aim board)
  trigger on|off switch a camera's external-trigger mode (debug)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2

DEFAULT_CAL = "calibration.json"
CAM_PORTS = {0: "camA", 1: "camB"}  # Pi 5 CSI port -> name; camA is on the left seen from behind the unit


def _calibration(args):
    from .calibration import load_calibration

    if not Path(args.calibration).exists():
        sys.exit(f"{args.calibration} not found: run `python -m launchmonitor calib solve` first (or use --sim)")
    return load_calibration(args.calibration)


def _rig_source(args):
    """A Rig, or a function returning the current Rig (IMU level + reference-edge aim)."""
    from .rig import two_camera_rig

    if getattr(args, "sim", False) and not Path(args.calibration).exists():
        return two_camera_rig()
    cal = _calibration(args)
    if args.aim == "board":
        if cal.R_world_unit_board is None:
            sys.exit("no board aim stored: run `python -m launchmonitor calib reaim`")
        return cal.rig(cal.R_world_unit_board)
    from .imu import ICM42688

    imu = ICM42688(bus=args.imu_bus)
    last = {"tilt": None}

    def current_rig():
        acc = imu.read_up()
        tilt = cal.tilt_deg(acc)
        if last["tilt"] is None or abs(tilt - last["tilt"]) > 0.3:
            print(f"level: unit tilted {tilt:.1f} deg from its calibration position (corrected automatically)")
            if tilt > 10:
                print("WARNING: more than 10 deg of tilt: is the unit sitting flat?")
            last["tilt"] = tilt
        return cal.rig(cal.world_from_imu(acc))

    return current_rig


def cmd_run(args):
    from .app import LaunchMonitor
    from .gspro import DEFAULT_PORT, GSProClient

    rig = _rig_source(args)
    gspro = None
    if args.gspro:
        host, _, port = args.gspro.partition(":")
        gspro = GSProClient(host, int(port or DEFAULT_PORT))
    if args.sim:
        from .sim_source import SimulatedLaunchMonitor

        sim = SimulatedLaunchMonitor(rig() if callable(rig) else rig, seed=args.seed, interval_s=args.sim_interval)
        pico, frames = sim, sim
    else:
        from .capture import PiCameraSource
        from .pico_link import PicoSerial

        pico = PicoSerial(args.pico)
        frames = PiCameraSource(CAM_PORTS, exposure_us=args.exposure_us, gain=args.gain)
        frames.start()
    print("ready" + (f", sending to GSPro at {args.gspro}" if gspro else ""))
    try:
        LaunchMonitor(rig, pico, frames, gspro, args.shots).run(args.count)
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(frames, "stop"):
            frames.stop()


def cmd_replay(args):
    from .app import format_result
    import numpy as np

    from .pipeline import load_shot, process_shot
    from .rig import two_camera_rig

    cal = None if (args.sim and not Path(args.calibration).exists()) else _calibration(args)
    for d in args.dirs:
        frames, pico, data = load_shot(d)
        if cal is None:
            rig = two_camera_rig()
        elif "R_world_unit" in data:  # the level + aim in use when the shot was taken
            rig = cal.rig(np.array(data["R_world_unit"]))
        elif cal.R_world_unit_board is not None:
            rig = cal.rig(cal.R_world_unit_board)
        else:
            sys.exit(f"{d}: no level/aim saved with the shot and no board aim in the calibration")
        _, r = process_shot(frames, pico, rig)
        print(f"{d}\n{format_result(r)}\n")


def cmd_calib_board(args):
    from .calibration import Board, board_print_image

    cv2.imwrite(args.out, board_print_image(Board()))
    print(f"wrote {args.out}: print at 100% (no 'fit to page'), landscape, then measure a square")


def _free_running_cameras():
    from .capture import PiCameraSource

    src = PiCameraSource(CAM_PORTS, exposure_us=20000, gain=4.0, trigger=False)
    src.start()
    return src


def cmd_calib_capture(args):
    from .calibration import Board, detect

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    board, src, n = Board(), _free_running_cameras(), 0
    print(f"Hold the board in front of the unit; move and tilt it between captures. Saving {args.pairs} pairs.")
    try:
        last = 0.0
        while n < args.pairs:
            frames = src.collect(1.0)
            if not frames or time.monotonic() - last < args.interval:
                continue
            seen = {k: detect(v, board) is not None for k, v in frames.items()}
            if all(seen.values()):
                for name, img in frames.items():
                    cv2.imwrite(str(out / f"pair{n:02d}_{name}.png"), img)
                n, last = n + 1, time.monotonic()
                print(f"  pair {n}/{args.pairs}")
        input("\nREFERENCE EDGE: stand the board upright on the mat facing the unit, TARGET arrow pointing the\n"
              "same way as the unit's reference edge, the board parallel to that edge (measure the gap at both\n"
              "ends of the board: equal within 1 mm). Check the board is vertical with a level. Press Enter.")
        frames = _grab(src)
        for name, img in frames.items():
            cv2.imwrite(str(out / f"edge_{name}.png"), img)
        if not args.no_imu:
            from .imu import ICM42688

            imu, readings = ICM42688(bus=args.imu_bus), []
            steps = ["sitting flat, as for the edge capture", "front raised ~5 mm on a shim", "back raised ~5 mm",
                     "left side raised ~5 mm", "right side raised ~5 mm"]
            print("\nIMU: leave the board exactly where it is. Tilt only the unit, as asked.")
            for k, step in enumerate(steps):
                input(f"  unit {step}; keep it still and press Enter")
                acc = imu.read_up(400)
                img = _grab(src)[CAM_PORTS[0]]
                cv2.imwrite(str(out / f"tilt{k}_{CAM_PORTS[0]}.png"), img)
                readings.append(acc.tolist())
            (out / "imu.json").write_text(json.dumps({"readings": readings}, indent=1))
        print(f"saved to {out}; next: python -m launchmonitor calib solve {out}")
    finally:
        src.stop()


def _grab(src):
    frames = None
    while not frames:
        frames = src.collect(1.0)
    return frames


def _read(p):
    return cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)


def _board(args):
    from .calibration import Board

    b = Board()
    if getattr(args, "square_mm", None):
        b = Board(square_m=args.square_mm / 1000, marker_m=(args.marker_mm or args.square_mm * b.marker_m / b.square_m) / 1000)
    return b


def cmd_calib_solve(args):
    from .calibration import calibrate_from_images, save_calibration

    d = Path(args.dir)
    a, b = CAM_PORTS[0], CAM_PORTS[1]
    pairs = [(_read(p), _read(str(p).replace(f"_{a}.png", f"_{b}.png"))) for p in sorted(d.glob(f"pair*_{a}.png"))]
    edge = (_read(d / f"edge_{a}.png"), _read(d / f"edge_{b}.png"))
    tilts = None
    if (d / "imu.json").exists():
        readings = json.loads((d / "imu.json").read_text())["readings"]
        tilts = [(_read(d / f"tilt{k}_{a}.png"), r) for k, r in enumerate(readings)]
    cal, report = calibrate_from_images(pairs, edge, _board(args), (a, b), tilts)
    save_calibration(cal, args.out, {"report": report})
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"wrote {args.out}")
    if report["stereo_rms_px"] > 0.5:
        print("WARNING: stereo error above 0.5 px: check the board is flat and the cameras didn't move")
    if tilts is None:
        print("No IMU captures: only `run --aim board` will work (after `calib reaim`).")


def cmd_calib_reaim(args):
    from .calibration import load_calibration, reaim, save_calibration

    cal = load_calibration(args.calibration)
    src = _free_running_cameras()
    try:
        input("Stand the board upright on the mat facing the unit, TARGET arrow toward the target, checked\n"
              "vertical with a level. Press Enter.")
        frames = _grab(src)
    finally:
        src.stop()
    save_calibration(reaim(cal, frames[CAM_PORTS[0]], _board(args)), args.calibration,
                     {"reaimed": time.strftime("%Y-%m-%d %H:%M")})
    print(f"updated {args.calibration}; use it with `run --aim board`")


def cmd_trigger(args):
    from .imx296 import PI5_BUS, Sensor

    with Sensor(PI5_BUS[args.port]) as s:
        s.set_trigger(args.state == "on")
    print(f"camera on CSI port {args.port}: trigger {args.state}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m launchmonitor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the launch monitor")
    r.add_argument("--calibration", default=DEFAULT_CAL)
    r.add_argument("--aim", choices=["imu", "board"], default="imu",
                   help="imu: automatic level + reference-edge aim (default); board: last `calib reaim`")
    r.add_argument("--imu-bus", type=int, default=1)
    r.add_argument("--pico", default="/dev/ttyACM0")
    r.add_argument("--gspro", help="GSPro PC address, host[:port] (default port 921)")
    r.add_argument("--shots", default="shots", help="directory for saved shots ('' to disable)")
    r.add_argument("--exposure-us", type=int, default=8000)
    r.add_argument("--gain", type=float, default=2.0)
    r.add_argument("--count", type=int, help="stop after N shots")
    r.add_argument("--sim", action="store_true", help="simulated cameras + Pico (no hardware)")
    r.add_argument("--sim-interval", type=float, default=2.0, help="seconds between simulated shots")
    r.add_argument("--seed", type=int, default=0)
    r.set_defaults(fn=cmd_run)

    rp = sub.add_parser("replay", help="re-process saved shots")
    rp.add_argument("dirs", nargs="+")
    rp.add_argument("--calibration", default=DEFAULT_CAL)
    rp.add_argument("--sim", action="store_true", help="use the nominal simulated rig if no calibration")
    rp.set_defaults(fn=cmd_replay)

    c = sub.add_parser("calib", help="camera calibration").add_subparsers(dest="calib_cmd", required=True)
    cb = c.add_parser("board")
    cb.add_argument("--out", default="charuco_board.png")
    cb.set_defaults(fn=cmd_calib_board)
    cc = c.add_parser("capture")
    cc.add_argument("--out", default="calib")
    cc.add_argument("--pairs", type=int, default=20)
    cc.add_argument("--interval", type=float, default=1.5)
    cc.add_argument("--no-imu", action="store_true", help="skip the IMU tilt captures")
    cc.add_argument("--imu-bus", type=int, default=1)
    cc.set_defaults(fn=cmd_calib_capture)
    cs = c.add_parser("solve")
    cs.add_argument("dir", nargs="?", default="calib")
    cs.add_argument("--out", default=DEFAULT_CAL)
    cs.set_defaults(fn=cmd_calib_solve)
    cr = c.add_parser("reaim")
    cr.add_argument("--calibration", default=DEFAULT_CAL)
    for p in (cs, cr):
        p.add_argument("--square-mm", type=float, help="measured printed square size (default 26)")
        p.add_argument("--marker-mm", type=float, help="measured marker size (default scales with --square-mm)")
    cr.set_defaults(fn=cmd_calib_reaim)

    t = sub.add_parser("trigger", help="camera external-trigger mode on/off")
    t.add_argument("state", choices=["on", "off"])
    t.add_argument("--port", type=int, choices=[0, 1], default=0, help="CSI port")
    t.set_defaults(fn=cmd_trigger)

    args = ap.parse_args(argv)
    if getattr(args, "shots", None) == "":
        args.shots = None
    args.fn(args)


if __name__ == "__main__":
    main()
