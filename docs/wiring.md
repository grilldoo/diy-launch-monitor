# Wiring

UNVERIFIED: written before the hardware has been bench-tested. Measure before you connect.

## Pico 2 pin map (firmware/pico/src/main.c)

| Pico pin | Signal | Connects to |
|---|---|---|
| GP2 | GATE1 in | Gate 1 comparator output (rising edge = club present) |
| GP3 | GATE2 in | Gate 2 comparator output |
| GP15 | STROBE out | TC4427 input, then MOSFET gates (high = LEDs on) |
| GP16 | CAM0 trigger | Camera A XTR, through the level stage below |
| GP17 | CAM1 trigger | Camera B XTR |
| GP18 | CAM2 trigger | Stage 2 club camera A |
| GP19 | CAM3 trigger | Stage 2 club camera B |
| USB | serial + power | Pi 5 USB port |
| GND | ground | Common ground with the Pi, cameras and LED driver |

## Camera trigger level
The GS camera's XTR input is 1.8 V logic. Don't drive it straight from the Pico's 3.3 V. Use
the circuit in Raspberry Pi's GS camera external-trigger documentation (or a small NPN or
N-MOSFET pulling XTR to GND). An open-drain pull-down is naturally active low, which matches
`CAM_TRIG_ACTIVE_LOW 1`.

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
