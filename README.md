# DIY Launch Monitor

An open, battery-powered, camera-based golf launch monitor inspired by the Foresight
GC3 / GCQuad. It sits beside the ball, needs no in-bay calibration, and sends ball
**and club** data to GSPro.

* **Ball:** speed, vertical/horizontal launch, total spin, backspin, sidespin, spin axis, carry
* **Club:** speed, path, attack angle, face to target, dynamic loft, face to path, smash
* **Hardware:** Raspberry Pi 5, Pi Global Shutter cameras, IR strobe, Pi Pico 2 timing controller
* **Cost:** about $565 for 2 cameras; about $865 for the GCQuad-style 4-camera build

> Status: **pre-hardware.** The simulator, solver, flight model, GSPro client and Pico timing
> firmware are written and tested against synthetic shots. Nothing has run on real hardware
> yet. Camera capture and real image detection come next.

## Docs
* [Design](docs/design.md): how it works, conventions, timing, simulated accuracy, risks
* [Bill of materials](docs/bom.md)
* [Wiring](docs/wiring.md)

## Repo layout
```
src/launchmonitor/   Python package that runs on the Pi
  camera.py          pinhole model + N-view triangulation
  rig.py             2- and 4-camera rig geometry
  schedule.py        flash/exposure schedule (mirror of the Pico firmware)
  sim.py             synthetic shots: ideal detections + rendered IR frames
  detect.py          ball detection in frames
  solver.py          detections -> ball, spin and club data
  flight.py          ball-flight model (carry)
  gspro.py           GSPro Open Connect v1 client
  pico_link.py       parse Pico serial output
firmware/pico/       Pico 2 timing controller (C, Pico SDK)
  host/              host-built unit tests + schedule CLI (no SDK needed)
tools/               accuracy_study.py: 2- vs 4-camera Monte Carlo
tests/               pytest suite
```

## Development
```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                                  # Python tests (also builds/compares the C schedule)
make -C firmware/pico/host test         # C unit tests on the host
python tools/accuracy_study.py          # accuracy table in docs/design.md
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
4. **Club:** gates, club sticker detection, face/path
5. **Package:** enclosure, battery, IMU auto-level, alignment-stick aim, phone page
6. **Stage 2 and outdoor:** dedicated club camera pair; 940 nm outdoor kit
