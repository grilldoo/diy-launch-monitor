# Wiring

UNVERIFIED: written before the hardware has been bench-tested. Measure before you connect.

## Pico 2 pin map (firmware/pico/src/main.c)

| Pico pin | Signal | Connects to |
|---|---|---|
| GP2 | GATE1 in | Gate 1 comparator output (rising edge = club present) |
| GP3 | GATE2 in | Gate 2 comparator output |
| GP15 | STROBE out | TC4427 input, then MOSFET gates (high = LEDs on) |
| GP16 | CAM0 trigger | ULN2003A IN1, then OUT1 to camera A J3 pin 2 (TRIG-) |
| GP17 | CAM1 trigger | ULN2003A IN2, then OUT2 to camera B J3 pin 2 (TRIG-) |
| GP18 | CAM2 trigger | Stage 2 club camera A |
| GP19 | CAM3 trigger | Stage 2 club camera B |
| USB | serial + power | Pi 5 USB port |
| GND | ground | Common ground with the Pi, cameras and LED driver |

## Camera trigger (InnoMaker CAM-IMX296Mono-GS, header J3)
From InnoMaker's manual (CAM-IMX296RAW-UserManual V2.0.2):

| J3 pin | Name | Meaning |
|---|---|---|
| 1 | TRIG+ | 3.3-5 V external trigger input (anode of the on-board PS2901 opto LED, with a 200 Ω resistor on board) |
| 2 | TRIG- | external ground (opto LED cathode) |

The opto output pulls the sensor's trigger line high while the LED is lit, and **the sensor
triggers on the falling edge** (LED turning off). InnoMaker's own example idles the GPIO high
and pulses it low for 3 ms per frame. Each lit LED draws ~15 mA, all the time between shots,
so the Pico doesn't drive it directly. Use one ULN2003A for all four cameras:

```
 +5V ------------------------- J3 pin 1 (TRIG+)   (each camera)
 Pico GP16..19 -> ULN2003A IN1..4
 ULN2003A OUT1..4 ------------ J3 pin 2 (TRIG-)   (one output per camera)
 ULN2003A pin 8 (GND) -------- common GND
```

Pico pin high: the ULN2003A output sinks, the LED is on, idle. Pin low: the LED is off and
exposure starts. That's `CAM_TRIG_ACTIVE_LOW 1` in `main.c`. The isolated inputs mean the
cameras' trigger grounds don't fight with the Pi's.

Software side (from the same manual):
* `/boot/firmware/config.txt`: `camera_auto_detect=0`, `dtoverlay=imx296,cam0` and `dtoverlay=imx296,cam1`.
* Enable trigger mode per camera over I2C with InnoMaker's `i2c.py trigger on --bus 6` (CAM0)
  and `--bus 4` (CAM1), with the stream stopped. Their repo: https://github.com/INNO-MAKER/cam-imx296raw-trigger
* libcamera needs a long frame timeout in trigger mode (`camera_timeout_value_ms`), or it gives
  up waiting between shots.

UNVERIFIED (bench test): whether the low-pulse width sets the exposure (the IMX296's
pulse-width trigger mode) or the libcamera exposure setting does. Either works if the exposure
covers the whole flash burst. Also unmeasured: the opto's turn-off delay. The firmware opens the
exposure 300 µs early (`exposure_lead_us`) to absorb it. Check with a logic analyser on the
camera's strobe output (J2) if needed.

## LED driver (one channel per string of LEDs)
```
 12V rail --+-- [capacitor bank] -- GND
            |
            +-- R_set -- LED -- LED -- LED --+
                                             D
 Pico GP15 -> TC4427 in   TC4427 out ------- G  IRLZ44N
                                             S
                                            GND
```
* 4 strings of 3 LEDs. Set R_set for the pulse current from the LED datasheet's pulse rating.
* Firmware caps pulses at 40 µs and enforces a 1.5 s lockout between shots, so the average
  power stays tiny.
* Keep the LED-to-capacitor loop short and thick. That's where the amps flow.

## Gate sensor (each gate)
```
 940 nm IR LED (constant)  --> retro-reflective dot on the mat --> BPW34 photodiode
 BPW34 -> MCP6002 transimpedance amp -> AC coupling -> LM393 comparator -> Pico GPx
```
A club passing through the beam causes a sharp drop in returned light. AC coupling ignores
slow changes in ambient light. Set the comparator threshold with a trimpot.

## Power
3S pack -> fuse -> switch -> {5 V/5 A buck -> Pi 5 USB-C}, {12 V rail -> LED driver}.
The Pico takes power from the Pi over USB. The IMU is on the Pi's I2C (GPIO2/3, 3.3 V).
