# Bill of materials

Prices are rough USD estimates (late 2026) to plan with, not quotes. Part numbers are
suggestions; equivalents are fine unless noted. Everything is built **4-camera ready**:
stage 1 leaves space and wiring for stage 2.

## Stage 1: two cameras (~$530-600)

| # | Part | Qty | Est. | Notes |
|---|---|---|---|---|
| 1 | Raspberry Pi 5, 8 GB | 1 | $80 | |
| 2 | Pi 5 Active Cooler | 1 | $5 | Sustained vision load throttles without it |
| 3 | microSD 64 GB (A2) or NVMe HAT + SSD | 1 | $12 | NVMe is nicer for saving raw shot frames |
| 4 | **InnoMaker CAM-IMX296Mono-GS** (old name CAM-MIPI296RAW / CAM-IMX296RAW), mono IMX296 global shutter | 2 | $90-150 | Mono version has **no IR-cut filter**; opto-isolated hardware trigger on J3, no board mod. Not the Colour version (IR-cut fitted) or the official Pi GS camera (colour, IR-cut). Comes with an M12 2.8 mm lens (too wide; keep as a spare) and a CS lens seat |
| 5 | M12 (S-mount, M12x0.5) lens, **6 mm**, for 1/2.9" or larger sensors, **no IR-cut filter** | 2 | $20-30 | Many M12 lenses ship with a 650 nm IR-cut: avoid those. Look for "no IR filter", "IR-corrected" or "850 nm" |
| 6 | 850 nm bandpass filter, ~15-25 mm round, narrow band (10-30 nm) | 2 | $30 | Sits in a printed cap over the lens (designed once the lens is in hand) |
| 7 | Camera cables, Pi 5 type (22-to-15 pin), 300 mm | 2 | $6 | The InnoMaker board has the standard 15-pin connector |
| 7a | ULN2003A Darlington driver (DIP-16) + socket | 1 | $2 | Drives the camera trigger inputs (all four channels) |
| 8 | Raspberry Pi Pico 2 (with headers) | 1 | $5 | Timing controller |
| 9 | OSRAM SFH 4715AS (850 nm high-power IR LED) on star boards | 12 | $45 | Check the pulse-current rating in the datasheet |
| 10 | LED driver: TC4427 gate driver (DIP-8), logic-level N-MOSFETs (e.g. IRLZ44N, TO-220), power resistors | 1 set | $15 | All through-hole, perfboard OK |
| 11 | Capacitor bank: low-ESR electrolytics, about 4 x 2200 µF 25 V | 1 set | $8 | Supplies the flash current so the battery doesn't have to |
| 12 | Gate sensors: BPW34 photodiodes x2, 940 nm IR LEDs x2, MCP6002 op-amp (DIP) + LM393 comparator (DIP), small lenses or printed tubes | 1 set | $12 | Through-hole |
| 13 | Retro-reflective tape (dots on the mat) | 1 | $8 | |
| 14 | **ICM-42688-P** IMU breakout (I2C, 3.3 V) | 1 | $10-15 | Automatic level. Pick this over the MPU-6050: its offset drifts far less with temperature (about 0.2° vs 1° of level error over a 20 °C swing). Mount it rigidly on the camera extrusion |
| 14a | Shims for the IMU calibration: 2 x 5 mm (washers, or a printed step) | - | $0 | Build time only |
| 15 | 3S2P 21700 Li-ion pack with BMS (~10 Ah, ~100 Wh) | 1 | $55 | Or build from cells + 3S BMS board |
| 16 | 3S charger (12.6 V) + DC jack | 1 | $15 | |
| 17 | 5 V / 5 A buck converter (Pi 5 needs 5 A for full USB power) | 1 | $15 | |
| 18 | 12 V regulator or boost for LED rail | 1 | $8 | |
| 19 | Power switch, fuse holder + fuse, XT30 connectors | 1 set | $10 | Fuse the pack |
| 20 | 2020 aluminium extrusion 300 mm + T-nuts + M3/M5 screws | 1 set | $15 | Rigid camera baseline; keeps calibration |
| 21 | Perfboard, headers, JST connectors, wire, heat shrink | 1 set | $15 | |
| 22 | PETG filament, 1 kg | 1 | $20 | PETG is fine for the A1 Mini (no enclosure needed); handles warmth better than PLA |
| 23 | Ball marking: Sakura Pigma Micron 05 (black) + printed jig | 1 | $8 | Carbon pigment ink shows up in IR |
| 24 | Matte white sticker paper (laser or inkjet) for the club stickers | 1 | $10 | One sticker per club; see docs/printing.md |
| 25 | Checkerboard calibration target (print on foam board) | 1 | $5 | |
| 26 | Line laser module (optional, shows ball position) | 1 | $5 | |
| | **Stage 1 total** | | **~$530-600** | |

## Stage 2: dedicated club camera pair (+~$270-350)

| # | Part | Qty | Est. | Notes |
|---|---|---|---|---|
| 27 | Raspberry Pi 5, 8 GB + Active Cooler + microSD | 1 | $95 | Second Pi; linked to the first with a short Ethernet cable |
| 28 | InnoMaker CAM-IMX296Mono-GS | 2 | $90-150 | |
| 29 | M12 lens, **12 mm**, 1/2.9"+, no IR-cut filter | 2 | $30-50 | Tighter view of the last 10 cm before impact |
| 30 | 850 nm bandpass filters | 2 | $30 | |
| 31 | Upgrade pack to 3S3P (~15 Ah) | 1 | +$25 | Keeps ~6 h runtime with two Pis |
| | **Stage 2 total** | | **~$270-350** | |

## Outdoor kit (optional, +~$60)
940 nm LEDs (12), 940 nm bandpass filters (2 or 4), printed sun hood.

## Tools
Bambu A1 Mini (yours), soldering iron with a fine tip, multimeter. No fine-pitch soldering is
needed: the cameras' trigger inputs are on pin headers. A cheap USB logic analyser ($10) helps
check strobe timing.

## Validation
Book a session on a GC3, GCQuad or Trackman with this unit set up alongside it. Recorded
shots from both become the ground-truth set for tuning.
