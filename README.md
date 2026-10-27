# DIY Launch Monitor

An open, battery-powered, camera-based golf launch monitor inspired by the Foresight
GC3 / GCQuad. It sits beside the ball, needs no in-bay calibration, and sends ball
**and club** data to GSPro.

* **Ball:** speed, vertical/horizontal launch, total spin, backspin, sidespin, spin axis, carry
* **Club:** speed, path, attack angle, face to target, dynamic loft, face to path, smash
* **Hardware:** Raspberry Pi 5, InnoMaker IMX296 mono global-shutter cameras, IR strobe, Pi Pico 2 timing controller
* **Cost:** about $565 for 2 cameras; about $865 for the GCQuad-style 4-camera build

> Status: **pre-hardware.** Everything from camera capture to GSPro is written: Pico timing
> firmware, capture, ChArUco stereo calibration, image detection, ball-dot matching, solver,
> flight model, and the GSPro loop with shot saving and replay. All of it is tested against
> simulated shots and rendered frames, including lens distortion. Printable parts are in
> `cad/stl/`. Club data (speed, path, attack, face, loft) is read from the face sticker in the
> images. Nothing has run on real hardware yet.

## Docs
* [Design](docs/design.md): how it works, conventions, timing, simulated accuracy, risks
* [Bill of materials](docs/bom.md)
* [Wiring](docs/wiring.md)
* [3D printing](docs/printing.md): ball-marking jig, camera mounts, club marker stickers
* [Pi setup and first run](docs/pi-setup.md): OS, cameras, calibration, GSPro

## Repo layout
```
src/launchmonitor/   Python package that runs on the Pi
  camera.py          pinhole model + N-view triangulation
  rig.py             2- and 4-camera rig geometry
  schedule.py        flash/exposure schedule (mirror of the Pico firmware)
  sim.py             synthetic shots: ideal detections + rendered IR frames
  detect.py          ball + dot detection in frames
  dots.py            ball-dot matching (which dot is which)
  data/              ball_pattern.json, the fixed marking pattern
  solver.py          detections -> ball, spin and club data
  flight.py          ball-flight model (carry)
  gspro.py           GSPro Open Connect v1 client
  pico_link.py       Pico serial link
  capture.py         picamera2 capture in trigger mode, frame pairing
  imx296.py          camera trigger-mode registers over I2C
  calibration.py     ChArUco intrinsics, stereo and aim calibration
  pipeline.py        frames -> result, save/replay shots
  app.py             main loop (Pico -> cameras -> solver -> GSPro)
  sim_source.py      simulated Pico + cameras for running everything off-hardware
  __main__.py        CLI: run, replay, calib, trigger
firmware/pico/       Pico 2 timing controller (C, Pico SDK)
  host/              host-built unit tests + schedule CLI (no SDK needed)
cad/                 OpenSCAD sources, generated includes, STLs, club marker sheet
tools/               accuracy_study.py (2- vs 4-camera), make_ball_pattern.py, export_cad.py
tests/               pytest suite
```

## Development
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                  # Python tests (also builds/compares the C schedule)
make -C firmware/pico/host test         # C unit tests on the host
python tools/accuracy_study.py          # accuracy table in docs/design.md
python tools/export_cad.py              # regenerate cad/ outputs (needs openscad)
python -m launchmonitor run --sim       # whole app with simulated shots (add --gspro HOST to test GSPro)
```

Firmware for the Pico 2:
```bash
export PICO_SDK_PATH=/path/to/pico-sdk   # SDK 2.x
cd firmware/pico && cmake -B build -DPICO_BOARD=pico2 && cmake --build build
# hold BOOTSEL, plug in the Pico, copy build/lm_timing_controller.uf2 to it
```

## Roadmap
1. **Bench test:** Pico + LEDs + one camera; multi-flash frame of a hand-dropped ball (`TEST 20` over serial)
2. **Ball data:** stereo calibration, Pi capture, real ball detection, GSPro hookup
3. **Spin:** marked balls, dot detection and correspondence
4. **Club:** gates, sticker detection on real frames, per-club face offset for woods
5. **Package:** enclosure (with the reference edge and sight notches), battery, phone page
6. **Stage 2 and outdoor:** dedicated club camera pair; 940 nm outdoor kit
