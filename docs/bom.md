# Bill of materials

Sourced October 2026. **Prices move:** "seen" prices come from the linked listing (or a search
snapshot of it) and should be re-checked before ordering. "Typical" prices are for generic parts
where any reputable seller will do. Shipping and tax aren't included. Everything is built
**4-camera ready**: stage 1 leaves space and wiring for stage 2.

## Stage 1: two cameras (~$750 as specified, ~$650 with the budget swaps below)

### Computer and cameras
| # | Part (specific model) | Qty | Price | Where | How it fits the build |
|---|---|---|---|---|---|
| 1 | **Raspberry Pi 5, 4 GB** | 1 | ~$85 (seen) | Any Raspberry Pi approved reseller | RAM prices pushed the 8 GB to ~$135-200 in 2026 ([Tom's Hardware](https://www.tomshardware.com/raspberry-pi/component-shortages-drive-raspberry-pi-prices-up-by-up-to-23-percent-escalating-lpddr4-lpddr5-costs-trigger-the-third-price-hike-of-the-year)). The software uses well under 1 GB: 4 GB is plenty, and the 2 GB ($77.50) works too |
| 2 | Raspberry Pi 5 Active Cooler (official) | 1 | ~$5-10 (typical) | Pi reseller | Dot matching runs the CPU hard for ~1 s per shot; without it the Pi throttles |
| 3 | SanDisk Extreme 64 GB microSD (A2) | 1 | ~$12-15 (typical) | Any | Each saved shot is ~3 MB (two PNGs): 64 GB holds ~15,000 shots. NVMe is optional later |
| 4 | **InnoMaker CAM-IMX296Mono-GS** (listed as CAM-MIPI296RAW / CAM-IMX296RAW) | 2 | ~$78-80 each (seen) | [Newegg (Kenuco)](https://www.newegg.com/p/3C6-05G2-00VV3) or Amazon search "CAM-MIPI296RAW". Manual: [InnoMaker GitHub](https://github.com/INNO-MAKER/cam-imx296raw-trigger) | **Mono, not Colour** (Colour has an IR-cut filter). No IR filter, opto-isolated trigger on a header, Pi kernel driver. Ships with an M12 2.8 mm lens (too wide) and a CS seat |
| 5 | **Commonlands CIL361-F1.8-M12ANIR** (6.1 mm, M12, no filter) | 2 | $39 each (seen) | [commonlands.com](https://commonlands.com/products/ir-corrected-6mm-m12-lens-cil361) | Explicitly no IR-cut filter, and IR-corrected (stays in focus at 850 nm). Rated for 1/2.5" sensors, so it covers the IMX296 (1/2.9"). Gives ~44° across, matching the 6 mm the rig was designed around |
| 6 | **Commonlands CBP850-100C030** (850 nm bandpass, 10 mm round, 0.3 mm) | 2 | ~$9-12 each (6-7 mm sizes seen at $9-12; 10 mm price not shown) | [commonlands.com](https://commonlands.com/products/850nm-bandpass-filter) | Thin disc that sits inside the M12 lens holder over the sensor. No printed filter cap needed. Re-focus the lens after fitting. Optics-vendor 25 mm filters cost $100-225 |
| 7 | Adafruit 5819: Pi 5 camera cable, 22-pin to 15-pin, 300 mm | 2 | $3.16 each (seen) | [Adafruit](https://adafruit.com/product/5819) | The InnoMaker board has the standard 15-pin connector |
| 8 | Raspberry Pi Pico 2 with headers (SparkFun DEV-29127) | 1 | $6.60 (seen) | [SparkFun](https://www.sparkfun.com/raspberry-pi-pico-2-with-headers.html) | Timing controller (firmware builds in CI) |

### Strobe and triggers
| # | Part (specific model) | Qty | Price | Where | How it fits the build |
|---|---|---|---|---|---|
| 9 | **Intelligent LED Solutions ILH-IO01-85NB-SC201-WIR200** (OSRAM OSLON Black 850 nm on a 20 mm heatsink board, **pre-wired**, 40° optic) | 12 | ~£5.65 (~$7.50) each (seen, IW01 version) | [RS Components](https://uk.rs-online.com/web/p/ir-leds/0907168) (RS 907-168) | No surface-mount soldering: two wires per LED. The 40° optic concentrates light on the hitting area. The wide (IW01, [RS 907-170](https://uk.rs-online.com/web/p/ir-leds/0907170)) version also works with more LEDs |
| 10 | Microchip TC4427CPA (DIP-8) + 4x Infineon IRLZ44NPBF (TO-220) + 1 W resistors | 1 set | ~$10 (typical) | DigiKey / Mouser | LED driver, all through-hole |
| 11 | Panasonic EEU-FR1E222 (2200 µF 25 V low-ESR) | 4 | ~$1.20 each (typical) | DigiKey / Mouser | Supplies the flash current so the battery doesn't have to |
| 12 | TI ULN2003AN (DIP-16) + socket | 1 | ~$1 (typical) | DigiKey / Mouser | Drives the four camera trigger inputs |
| 13 | Gate sensors: 2x Vishay BPW34 (~$1.29 seen), MCP6002-I/P (DIP), TI LM393P (DIP, ~$0.60 seen), 2x Vishay TSAL6400 940 nm LEDs | 1 set | ~$6 | DigiKey / Mouser | Club speed and impact timing. 940 nm so the 850 nm-filtered cameras don't see them |
| 14 | 3M Scotchlite 8830 retro-reflective tape, 2 in x 10 ft | 1 | $17 (seen) | [AndyMark](https://www.andymark.com/products/3m-scotchlite-8830-series-retroreflective-tape) | Two small dots on the mat at 30 cm and 18 cm behind the ball. Cheaper generic retro-reflective tape works too |

### Level sensor
| # | Part (specific model) | Qty | Price | Where | How it fits the build |
|---|---|---|---|---|---|
| 15 | **Analog Devices EVAL-ADXL355-PMDZ** | 1 | $47.06 (seen; 1,285 in stock) | Mouser 584-EVAL-ADXL355PMDZ | Automatic level. Zero point drift **0.15 mg/°C max** ([Analog Devices](https://www.analog.com/en/products/adxl355.html)), so under 0.2° over a 20 °C swing. A consumer IMU (ICM-42688-P, ±1 mg/°C) could be ~1° off between a cold and a warm session, which is 1° of launch angle. SPI, wired to the Pi header (docs/wiring.md). Fallback supported in software: ICM-42688-P ([MikroE 6DOF IMU 14 Click](https://www.digikey.com/en/products/detail/mikroelektronika/MIKROE-4237/13166617), $30) |
| 15a | Shims for the build calibration: 2x 5 mm (washers or a printed step) | - | $0 | | Build time only |

### Power
| # | Part (specific model) | Qty | Price | Where | How it fits the build |
|---|---|---|---|---|---|
| 16 | **TalentCell YB1206000-USB** (12 V 6000 mAh / 66.6 Wh, built-in protection, **charger included**) | 1 | ~$40 (typical) | Amazon ASIN B00ME3ZH7C | Replaces the loose 3S pack + protection board + charger. 12 V out (9-12.6 V, 3 A max) on a 5.5 x 2.1 mm plug. ~8 W load gives ~7 h. One sealed, protected pack is the safer first build |
| 17 | Pololu D36V50F5 (5 V 5.5 A step-down) | 1 | $34.95-39.95 (seen) | [Pololu #4091](https://www.pololu.com/product/4091) | Feeds the Pi 5 (up to ~15 W) from the pack |
| 18 | Pololu S18V20F12 (12 V step-up/step-down) | 1 | $29.95 (seen) | [Pololu #2577](https://www.pololu.com/product/2577) | Holds the LED rail at 12 V as the pack runs down from 12.6 to 9 V, so flash brightness stays constant |
| 19 | 5.5 x 2.1 mm DC plug pigtail, inline 3 A fuse holder + fuse, rocker switch, USB-C pigtail (for the Pi) | 1 set | ~$10 (typical) | Any | |

### Mechanical and consumables
| # | Part (specific model) | Qty | Price | Where | How it fits the build |
|---|---|---|---|---|---|
| 20 | 2020 aluminium extrusion, 300 mm (e.g. MISUMI HFS5-2020-300, or any 2020 cut to length) | 1 | ~$8-15 (typical) | MISUMI / Amazon | Rigid camera baseline: keeps calibration |
| 21 | M5 T-nut + screw kit for 2020 | 1 | ~$9 (seen) | Amazon search "2020 M5 T-nut kit" | Camera mounts to extrusion |
| 22 | M2 x 8 self-tapping screws | 1 pack | ~$6 (typical) | Any | Camera boards to the printed mounts |
| 23 | Perfboard, pin headers, JST-XH connectors, 22 AWG wire, heat shrink | 1 set | ~$15 (typical) | Any | |
| 24 | Bambu PETG HF, 1 kg | 1 | ~$20-25 (typical) | Bambu store | All printed parts |
| 25 | Sakura Pigma Micron 05, black | 1-2 | ~$3-4 each (typical) | Any art/office store | Carbon pigment ink: dark at 850 nm, unlike most Sharpies |
| 26 | Avery matte white full-sheet labels (laser or inkjet, to match your printer) | 1 pack | ~$12 (typical) | Any office store | Club stickers (docs/printing.md) |
| 27 | Foam board (A4/Letter or larger) for the ChArUco board | 1 | ~$5 (typical) | Any | Board printed with `python -m launchmonitor calib board` |
| 28 | Line laser module (optional; shows where to tee the ball) | 1 | ~$6 (typical) | Any | Optional |
| | **Stage 1 total** | | **~$750** | | |

### Budget swaps (save ~$100)
* **Generic buck converters** instead of the two Pololus (save ~$45). Fine for a prototype; Pololu's are quieter and rated properly.
* **Bare SFH 4715AS LEDs** ([DigiKey](https://azcus.digikey.com/en/products/detail/ams-osram-usa-inc/SFH-4715AS/5254077), $3.06) on 20 mm star boards instead of the pre-wired modules (save ~$40-50). Needs reflow (a hot plate) or hot air, not iron soldering.
* **Raspberry Pi 5 2 GB** (save ~$7.50).
* **Generic retro-reflective tape** (save ~$10).

## Stage 2: dedicated club camera pair (+~$400)
| # | Part | Qty | Price | Notes |
|---|---|---|---|---|
| 29 | Raspberry Pi 5 4 GB + Active Cooler + microSD | 1 | ~$105 | Second Pi, linked to the first with a short Ethernet cable. Frame collection across two Pis is not written yet |
| 30 | InnoMaker CAM-IMX296Mono-GS | 2 | ~$160 | |
| 31 | **Commonlands CIL123-F2.3-M12ANIR** (12.5 mm, no filter) | 2 | $29 each (seen base price) | [commonlands.com](https://commonlands.com/products/ir-corrected-12mm-m12-lens-5mp). Tighter view of the last 10 cm before impact |
| 32 | Commonlands CBP850-100C030 | 2 | ~$20 | |
| 33 | Bigger battery: a 12 V pack of ~100 Wh | 1 | ~$60 | Two Pis draw ~15 W: the 66 Wh pack would give ~4 h |

## Outdoor kit (optional, +~$60)
940 nm LEDs (12) and 940 nm bandpass filters (2 or 4), plus a printed sun hood.

## Tools
* **Bambu A1 Mini:** ~$299 (US store, May 2026).
* **Soldering iron** with a fine tip, and a **multimeter**.
* **Optional: a USB logic analyser** (24 MHz, 8 channel, ~$12) to check strobe and trigger timing.
* No fine-pitch soldering is needed: the camera trigger inputs are on pin headers, and the LEDs and level sensor come on boards.

## Validation
Book a session on a GC3, GCQuad or Trackman with this unit set up alongside it. Recorded
shots from both become the ground-truth set for tuning.
