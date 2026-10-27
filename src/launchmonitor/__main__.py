"""Command line: python -m launchmonitor <command> ...

  run            the launch monitor (real hardware, or --sim)
  replay DIR..   re-process saved shots
  calib board    write the printable ChArUco board
  calib capture  save board image pairs from both cameras (free-running)
  calib solve    compute calibration.json from captured pairs
  calib reaim    re-do the world frame after moving the unit
  trigger on|off switch a camera's external-trigger mode (debug)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

DEFAULT_CAL = "calibration.json"
CAM_PORTS = {0: "camA", 1: "camB"}  # Pi 5 CSI port -> name; camA is on the left seen from behind the unit


def _rig(args):
    from .calibration import load_rig
    from .rig import two_camera_rig

    if getattr(args, "sim", False) and not Path(args.calibration).exists():
        return two_camera_rig()
    if not Path(args.calibration).exists():
        sys.exit(f"{args.calibration} not found: run `python -m launchmonitor calib solve` first (or use --sim)")
    return load_rig(args.calibration)


def cmd_run(args):
    from .app import LaunchMonitor
    from .gspro import DEFAULT_PORT, GSProClient

    rig = _rig(args)
    gspro = None
    if args.gspro:
        host, _, port = args.gspro.partition(":")
        gspro = GSProClient(host, int(port or DEFAULT_PORT))
    if args.sim:
        from .sim_source import SimulatedLaunchMonitor

        sim = SimulatedLaunchMonitor(rig, seed=args.seed, interval_s=args.sim_interval)
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
    from .pipeline import load_shot, process_shot

    rig = _rig(args)
    for d in args.dirs:
        frames, pico, _ = load_shot(d)
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
        input("Now stand the board upright on the mat facing the unit, TARGET arrow toward the target, "
              "checked vertical with a level. Press Enter to capture the aim pair.")
        frames = None
        while not frames:
            frames = src.collect(1.0)
        for name, img in frames.items():
            cv2.imwrite(str(out / f"aim_{name}.png"), img)
        print(f"saved to {out}; next: python -m launchmonitor calib solve {out}")
    finally:
        src.stop()


def _read(p):
    return cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)


def _board(args):
    from .calibration import Board

    b = Board()
    if getattr(args, "square_mm", None):
        b = Board(square_m=args.square_mm / 1000, marker_m=(args.marker_mm or args.square_mm * b.marker_m / b.square_m) / 1000)
    return b


def cmd_calib_solve(args):
    from .calibration import calibrate_from_images, save_rig

    d = Path(args.dir)
    a, b = CAM_PORTS[0], CAM_PORTS[1]
    pairs = [(_read(p), _read(str(p).replace(f"_{a}.png", f"_{b}.png"))) for p in sorted(d.glob(f"pair*_{a}.png"))]
    aim = (_read(d / f"aim_{a}.png"), _read(d / f"aim_{b}.png"))
    rig, report = calibrate_from_images(pairs, aim, _board(args), (a, b))
    save_rig(rig, args.out, {"report": report})
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"wrote {args.out}")
    if report["stereo_rms_px"] > 0.5:
        print("WARNING: stereo error above 0.5 px: check the board is flat and the cameras didn't move")


def cmd_calib_reaim(args):
    from .calibration import load_rig, reaim, save_rig

    rig = load_rig(args.calibration)
    src = _free_running_cameras()
    try:
        input("Stand the board upright on the mat facing the unit, TARGET arrow toward the target. Press Enter.")
        frames = None
        while not frames:
            frames = src.collect(1.0)
    finally:
        src.stop()
    save_rig(reaim(rig, frames[CAM_PORTS[0]], _board(args)), args.calibration, {"reaimed": time.strftime("%Y-%m-%d %H:%M")})
    print(f"updated {args.calibration}")


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
