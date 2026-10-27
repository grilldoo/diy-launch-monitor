# Raspberry Pi setup and first run

UNTESTED ON HARDWARE: written from the Raspberry Pi and InnoMaker documentation before
the parts arrived. Expect to adjust details on the first bench session.

## 1. Operating system
Raspberry Pi OS (64-bit, Bookworm or newer) on the Pi 5. Set the hostname, user (these docs
assume `golf`), Wi-Fi and SSH in Raspberry Pi Imager.

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git python3-venv python3-picamera2 python3-serial i2c-tools
sudo usermod -aG video,i2c,dialout golf     # cameras, camera I2C, Pico serial; log out and back in
```

## 2. Cameras
In `/boot/firmware/config.txt`:
```ini
camera_auto_detect=0
dtoverlay=imx296,cam0
dtoverlay=imx296,cam1
```
Reboot, then check both cameras appear:
```bash
rpicam-hello --list-cameras
sudo modprobe i2c-dev && ls /dev/i2c-*      # expect i2c-4 (CAM1) and i2c-6 (CAM0)
i2cdetect -y 6                              # the sensor answers at 0x1a
```
**Camera A** (left, seen from behind the unit) goes on **CAM0**, camera B on **CAM1**.

## 3. Software
```bash
git clone https://github.com/grilldoo/diy-launch-monitor.git
cd diy-launch-monitor
python3 -m venv --system-site-packages .venv   # sees apt's picamera2
# OpenCV from pip: the ChArUco API needs OpenCV 4.7+, and Bookworm's apt package is 4.6.
# numpy stays 1.x to match the apt-built picamera2 helpers.
.venv/bin/pip install -e . "numpy<2"
.venv/bin/python -m launchmonitor run --sim --count 3   # sanity check: simulated shots, no hardware
```
If `import picamera2` fails inside the venv with a numpy error, the pip numpy and the apt
packages disagree: remove the pip one (`.venv/bin/pip uninstall numpy`) so apt's is used.

## 4. Pico firmware
Download `lm_timing_controller.uf2` from the latest CI run on GitHub (Actions, then the run,
then Artifacts). Hold BOOTSEL, plug the Pico into the Pi, and copy the file to the drive that
appears. Check it responds:
```bash
python3 -m serial.tools.miniterm /dev/ttyACM0 115200    # type PING, expect {"type":"pong"}
```

## 5. Focus and calibration
1. **Focus:** with the lens filters fitted, run `rpicam-hello -t 0` (free-running) under
   halogen, incandescent or daylight (LED room lighting has almost no 850 nm). Turn each M12
   lens until a ball at the hitting spot is sharp, then lock the lens with its set screw.
2. **Print the board:** `python -m launchmonitor calib board`, then print `charuco_board.png`
   at 100%, landscape. Glue it to foam board or card so it's flat. Measure a square: if it isn't
   26.0 mm, pass the measured size as `--square-mm` below.
3. **Capture:** `python -m launchmonitor calib capture`. Hold the board 40-80 cm in front of the
   unit, in different positions and tilts, until 20 pairs are saved. For the final "aim" image,
   stand the board upright on the mat, printed side facing the unit and TARGET arrow pointing at
   the target. Check it's vertical with a level: 1° of lean is 1° of launch-angle error.
4. **Solve:** `python -m launchmonitor calib solve` writes `calibration.json`. Expect reprojection
   errors under 0.3 px and a baseline within a few mm of 200.
5. **Moving the unit** only needs the aim step again: `python -m launchmonitor calib reaim`.

## 6. Run
```bash
.venv/bin/python -m launchmonitor run --gspro <GSPro PC IP>
```
On the GSPro PC, enable the Open Connect API (port 921) and allow it through the firewall.
Every shot is saved under `shots/`. If a shot reads wrong, copy its folder off the Pi:
`python -m launchmonitor replay shots/<folder>` reproduces it anywhere, so it can be fixed
without the hardware. To start at boot, see `deploy/launchmonitor.service`.

## Bench-test order
1. Pico alone: `PING`, then `FLASH` with the LED driver connected (look at the LEDs through a
   phone camera: most phone cameras see 850 nm).
2. One camera in trigger mode: `python -m launchmonitor trigger on --port 0`, then send
   `TEST 20` to the Pico and check one frame arrives with the flashes in it.
3. Check whether the trigger pulse width or the `--exposure-us` setting controls exposure
   (docs/wiring.md, "Camera trigger"). Record which.
4. Drop a marked ball through the view and send `TEST 20`. You should see one frame with
   several ball images.
5. Wire the gates, then hit soft wedges into a net.
