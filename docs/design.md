# Design

A battery-powered, photometric (camera-based) launch monitor in the style of the
Foresight GC3 / GCQuad. It sits beside the ball, photographs the last few
centimetres of club travel and the first ~30 cm of ball flight, and needs no
in-bay calibration, so it can be set up anywhere: hitting mat, garage, range.

Radar units (Trackman-style) were rejected because indoors they need a long
flight and placement calibration. Cameras only need to see the impact zone.

## Coordinate system and sign conventions

Origin at the ball centre at address. `+x` toward the target, `+y` up, `+z`
away from a right-handed golfer (toward the unit). Internally everything is SI
(m, s, rad); results are reported in golf units.

| Quantity | Positive means |
|---|---|
| HLA (horizontal launch) | right of target |
| VLA (vertical launch) | up |
| Sidespin / spin axis | curves right (fade/slice for a right-hander) |
| Club path | in-to-out (right) |
| Face to target | open (right) |
| Attack angle | up |
| Face to path | face - path |

## Layout

```
                 target (+x) -->
   golfer (RH)        o ball
   -z side     [gate2]  [gate1] are spots on the mat 12 and 25 cm behind the ball
                          \
                           \  ~60-70 cm
                            [ UNIT ]  +z side, ~35 cm forward of the ball,
                                       yawed back toward the impact zone
```

The unit sits forward of the ball and looks back diagonally so the cameras can see
the club-face stickers at an angle. (From straight side-on, the face is edge-on.)
Placement constants live in `src/launchmonitor/rig.py`; `tests/test_rig.py`
checks that every club and ball position the solver needs is in frame.

## Hardware architecture

```
 3S Li-ion pack (BMS) --+-- 5V/5A buck --> Raspberry Pi 5 (8GB)  [+ 2nd Pi 5 in stage 2]
                        +-- 12V rail + capacitor bank --> LED driver --> 12x 850 nm IR LEDs
 Pi 5
  |- CSI0/CSI1 --> Global Shutter cameras (IMX296), 850 nm bandpass filters
  |- USB ------> Pico 2: gates in, camera triggers + strobe out (microsecond timing)
  |- I2C ------> IMU (auto-level)
  `- Wi-Fi ----> GSPro (Open Connect, TCP 921) / phone web page
```

### Stages
* **Stage 1, 2 cameras:** one stereo pair (6 mm lenses, 20 cm baseline) sees club and ball.
* **Stage 2, 4 cameras (GCQuad-style):** add a second Pi 5 and a dedicated club pair
  (12 mm lenses, tighter view of the last 10 cm before impact). The Pico already has four
  camera trigger outputs, so all four cameras are hardware-synchronised.

### Why a strobe instead of a high-speed camera
The cameras are 60 fps global-shutter sensors (about $50). One exposure stays open for
~3-6 ms while the IR LEDs flash 15 µs pulses. Every flash freezes the ball and club
(80 m/s x 15 µs = 1.2 mm blur), so one frame holds the whole sequence.

## Timing (firmware/pico/src/lm_timing.c, mirrored in schedule.py)

1. **Club gates.** Two retro-reflective optical gates (IR emitter + photodiode in the unit,
   aimed at small retro-reflective dots on the mat at 25 cm and 12 cm behind the ball). The
   clubhead breaks each return beam in turn.
2. **Club speed and impact time** come from the gate-to-gate time. Impact is predicted
   assuming constant speed over the last 12 cm.
3. **Flash plan:**
   * 3 club flashes, when the face is 9, 5 and 1.5 cm from the ball. Face angle and loft come
     from the last one (the face is still closing before that). Path, attack angle and
     club speed come from all three.
   * 5 ball flashes, spaced so the ball moves about 6 cm (1.4 diameters) between them, based on
     *expected* ball speed (1.35 x club speed). Ball images never overlap, even at a smash
     factor of 1.15 (`tests/test_rig.py`).
   * Too-fast swings drop the earliest club flash rather than miss the shot.
4. **Exposure** opens 50 µs before the first flash and closes 50 µs after the last.
5. The Pico prints the actual schedule as JSON. The solver uses those times, so the
   impact-prediction error only shifts flash timing; it doesn't corrupt the measurement.

### Camera trigger
The Pi Global Shutter camera supports external trigger through its XTR pad: the pulse width
sets the exposure. Per Raspberry Pi's documentation this needs a small hardware change on
each camera board (removing one SMD resistor and soldering wires to XTR and GND), and the
signal is 1.8 V logic. **That's the hardest soldering job in the build.** Follow the official
GS camera external-trigger instructions exactly. `CAM_TRIG_ACTIVE_LOW` in `main.c` must be
checked on the bench.

## Optics and lighting
* IMX296: 1456 x 1088, 3.45 µm pixels. With a 6 mm lens at ~65 cm the view is about 55 cm
  wide at 0.37 mm/px. A ball is about 115 px across.
* 850 nm bandpass filters reject most indoor light. Gate emitters are 940 nm, so the cameras
  don't see them.
* Outdoor kit (phase 6): swap to 940 nm LEDs and filters (the atmosphere absorbs some sunlight
  at 940 nm), add a sun hood and drive the LEDs harder. Gate emitters move to 850 nm with
  modulation.

## Markings
* **Ball:** 24 dots in a Fibonacci-sphere pattern, applied with a 3D-printed jig so every ball
  is identical. The ink must absorb IR: use carbon-pigment ink (e.g. Sakura Pigma Micron).
  Many Sharpie inks are invisible at 850 nm, so test under the strobe first.
* **Club:** 4 matte dots in an asymmetric layout (`FACE_MARKERS_UV` in `sim.py`) on a sticker
  on the face near the toe. The solver fits this known layout, which is better conditioned
  than a free plane fit.

## Solver (src/launchmonitor/solver.py)
1. Triangulate every detection seen by 2 or more cameras in the same flash (N-view DLT).
2. Ball: straight-line fit of centres vs. flash time gives speed, VLA and HLA.
3. Spin: Kabsch rotation of the ball dots between consecutive flashes gives angular velocity.
   That is split into backspin and sidespin around the launch direction.
4. Club: fit the known sticker layout in the last pre-impact flash for face and loft. A line fit
   of the sticker centroid over the club flashes gives speed, path and attack angle.
5. Ball flight model (`flight.py`) gives carry for the stand-alone readout. GSPro does its own.

## Simulated accuracy (detection noise only)

`python tools/accuracy_study.py --seeds 200`, 0.15 px detection noise, 1 sigma:

| Shot | Rig | Ball mph | VLA | HLA | Spin % | Axis | Club mph | Path | Attack | Face | Loft |
|---|---|---|---|---|---|---|---|---|---|---|---|
| driver | 2-camera | 0.08 | 0.01 | 0.07 | 0.34 | 0.39 | 0.21 | 0.14 | 0.03 | 0.56 | 0.65 |
| driver | 4-camera | 0.08 | 0.01 | 0.07 | 0.34 | 0.39 | 0.07 | 0.05 | 0.02 | 0.18 | 0.21 |
| 7-iron | 2-camera | 0.06 | 0.01 | 0.07 | 0.12 | 0.13 | 0.14 | 0.15 | 0.04 | 0.54 | 0.60 |
| 7-iron | 4-camera | 0.06 | 0.01 | 0.07 | 0.12 | 0.13 | 0.04 | 0.05 | 0.02 | 0.18 | 0.21 |
| wedge | 2-camera | 0.05 | 0.02 | 0.09 | 0.13 | 0.12 | 0.13 | 0.14 | 0.04 | 0.64 | 0.61 |
| wedge | 4-camera | 0.05 | 0.02 | 0.09 | 0.13 | 0.12 | 0.04 | 0.05 | 0.02 | 0.24 | 0.23 |

These are lower bounds. Real error will be higher, mostly from calibration, lens distortion,
detection bias, dot-correspondence mistakes and timing jitter, none of which are modelled yet.
What the table does show: **the dedicated club pair cuts face and loft error about 3x.** Ball
data doesn't change, since stage 2 doesn't touch the ball cameras.

## Setup at a new location
1. Place the unit using the printed spacing gauge (fixed offset from the ball).
2. The IMU measures tilt, and the solver rotates results into a level frame. (Planned)
3. Lay an alignment stick at the target and tap **Align**. The cameras detect the stick and
   store an aim offset. (Planned)
4. No other calibration. Stereo calibration is done once at build time with a checkerboard,
   and the rigid aluminium frame keeps it.

## Known risks / open questions
* **Dot correspondence:** the solver currently gets dot IDs from the simulator. Real detection
  must work out which dot is which across flashes and cameras. Options: dots of different
  sizes, or matching against the known pattern under candidate rotations.
* **High-spin aliasing:** wedges at 10,000 rpm turn about 90° between flashes. That's fine, but
  close to the 180° limit at low ball speed. Could add one extra closely spaced flash pair.
* **Club and ball overlap at impact:** the last club flash is 1.5 cm before contact. Check on
  real frames that stickers aren't hidden by the ball (the simulator ray-tests this).
* **Face closure:** the face keeps closing (roughly 0.5-1° at typical closure rates) between the last flash and impact. Correct it
  by extrapolating the face rotation from the three club flashes.
* **GSPro sign conventions:** verify on first hookup.
