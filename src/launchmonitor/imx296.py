"""IMX296 external-trigger control over I2C (InnoMaker CAM-IMX296Mono-GS).

The stock Raspberry Pi imx296 driver doesn't expose trigger mode, so InnoMaker's
tool writes sensor registers directly. The register sequence below is the one from
their i2c.py (github.com/INNO-MAKER/cam-imx296raw-trigger). The kernel driver already
owns address 0x1a, so this uses the I2C_RDWR ioctl, which doesn't claim the address.

Pi 5 buses: CAM0 = /dev/i2c-6, CAM1 = /dev/i2c-4.

UNVERIFIED on hardware. InnoMaker's manual is inconsistent about whether to enable
trigger mode before or after the stream starts: the README says "stream stopped", but
the dual-camera walkthrough starts the stream first. Starting the stream may rewrite
the sensor registers, so capture.PiCameraSource enables trigger mode *after* starting.
"""

from __future__ import annotations

from .i2c import I2C_RDWR, I2CDevice  # noqa: F401  (I2C_RDWR re-exported for tests)

SENSOR_ADDR = 0x1A
PI5_BUS = {0: 6, 1: 4}  # CSI port -> I2C bus

TRIGGER_ON = [
    (0x300A, 0x01),  # register hold (atomic update) start
    (0x3000, 0x01),  # standby
    (0x3000, 0x00),  # operating
    (0x300B, 0x01),  # trigger-related enable
    (0x30AE, 0x01),  # external trigger enable
    (0x300A, 0x00),  # register hold end
]
TRIGGER_OFF = [
    (0x300A, 0x01),
    (0x3000, 0x01),
    (0x3000, 0x00),
    (0x300B, 0x00),
    (0x30AE, 0x00),
    (0x300A, 0x00),
]


def reg_write_bytes(reg: int, val: int) -> bytes:
    """16-bit register address (big-endian) + 8-bit value, as the IMX296 expects."""
    return bytes([(reg >> 8) & 0xFF, reg & 0xFF, val & 0xFF])


class Sensor(I2CDevice):
    def __init__(self, bus: int, addr: int = SENSOR_ADDR, ioctl=None):
        super().__init__(bus, addr, reg16=True, ioctl=ioctl)

    def set_trigger(self, on: bool) -> None:
        for reg, val in TRIGGER_ON if on else TRIGGER_OFF:
            self.write(reg, val)
