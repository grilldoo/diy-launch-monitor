"""Accelerometer for automatic levelling.

At rest an accelerometer measures +1 g pointing *up* (the reaction to gravity), so the
normalised average reading is the "up" direction in the sensor's own axes. calibration.py
turns that into "up" in the cameras' frame.

1 deg of level error is 1 deg of launch-angle error, so what matters is how far the
sensor's zero point drifts with temperature between the build calibration and a cold
or hot session:
  * ADXL355 (default, EVAL-ADXL355-PMDZ board, SPI): 0.15 mg/degC max (Analog Devices'
    guaranteed spec) -> under 0.2 deg over a 20 degC swing.
  * ICM-42688-P (I2C): +-1 mg/degC listed in distributor copies of the datasheet -> up
    to ~1 deg over 20 degC. Kept as a fallback.

UNVERIFIED on hardware. Register maps are from memory of the datasheets:
  ADXL355: SPI mode 0, first byte (reg << 1) | 1 to read; DEVID_AD 0x00 = 0xAD,
  PARTID 0x02 = 0xED, XDATA3 0x08..ZDATA1 0x10 (20-bit, left-justified, two's
  complement), RANGE 0x2C (0x81 = +-2 g), POWER_CTL 0x2D (0 = measure),
  FILTER 0x28 (0x05 = 125 Hz), +-2 g = 256000 LSB/g.
  ICM-42688-P (bank 0): WHO_AM_I 0x75 = 0x47, PWR_MGMT0 0x4E, ACCEL_CONFIG0 0x50,
  ACCEL_DATA_X1 0x1F (big-endian X, Y, Z), +-2 g = 16384 LSB/g.
"""

from __future__ import annotations

import time

import numpy as np

from .i2c import I2CDevice

ADDR = 0x68  # AP_AD0 low; 0x69 if high
WHO_AM_I, WHO_AM_I_VALUE = 0x75, 0x47
PWR_MGMT0 = 0x4E
ACCEL_CONFIG0 = 0x50
ACCEL_DATA_X1 = 0x1F
LSB_PER_G = 16384.0


class ICM42688:
    def __init__(self, bus: int = 1, addr: int = ADDR, ioctl=None):
        self.dev = I2CDevice(bus, addr, ioctl=ioctl)
        who = self.dev.read(WHO_AM_I, 1)[0]
        if who != WHO_AM_I_VALUE:
            raise RuntimeError(f"ICM-42688 not found at 0x{addr:02x} on i2c-{bus} (WHO_AM_I 0x{who:02x})")
        self.dev.write(ACCEL_CONFIG0, 0x66)  # +-2 g, 1 kHz output rate
        self.dev.write(PWR_MGMT0, 0x03)  # accelerometer low-noise mode, gyro off
        time.sleep(0.05)

    def read_g(self) -> np.ndarray:
        raw = self.dev.read(ACCEL_DATA_X1, 6)
        return np.frombuffer(raw, dtype=">i2").astype(float) / LSB_PER_G

    def read_up(self, n: int = 200, interval_s: float = 0.002) -> np.ndarray:
        """Average of n readings (~0.4 s): the up direction in IMU axes, in g (|a| ~ 1)."""
        acc = np.zeros(3)
        for _ in range(n):
            acc += self.read_g()
            time.sleep(interval_s)
        return acc / n

    def close(self) -> None:
        self.dev.close()


class ADXL355:
    """ADXL355 over SPI (spidev; on the Pi: sudo apt install python3-spidev, enable SPI)."""

    DEVID_AD, PARTID = 0x00, 0x02
    XDATA3 = 0x08
    FILTER, RANGE, POWER_CTL = 0x28, 0x2C, 0x2D
    LSB_PER_G = 256000.0

    def __init__(self, bus: int = 0, device: int = 0, spi=None):
        if spi is None:
            import spidev  # noqa: PLC0415

            spi = spidev.SpiDev()
            spi.open(bus, device)
            spi.mode = 0
            spi.max_speed_hz = 1_000_000
        self.spi = spi
        devid, partid = self._read(self.DEVID_AD, 1)[0], self._read(self.PARTID, 1)[0]
        if (devid, partid) != (0xAD, 0xED):
            raise RuntimeError(f"ADXL355 not found on spidev{bus}.{device} (ids 0x{devid:02x} 0x{partid:02x})")
        self._write(self.RANGE, 0x81)  # +-2 g
        self._write(self.FILTER, 0x05)  # 125 Hz output rate, matching low-pass
        self._write(self.POWER_CTL, 0x00)  # leave standby: measure
        time.sleep(0.1)

    def _read(self, reg: int, n: int) -> bytes:
        return bytes(self.spi.xfer2([(reg << 1) | 1] + [0] * n)[1:])

    def _write(self, reg: int, val: int) -> None:
        self.spi.xfer2([reg << 1, val & 0xFF])

    def read_g(self) -> np.ndarray:
        raw = self._read(self.XDATA3, 9)
        out = []
        for i in range(3):
            v = (raw[3 * i] << 12) | (raw[3 * i + 1] << 4) | (raw[3 * i + 2] >> 4)
            if v & 0x80000:  # 20-bit two's complement
                v -= 1 << 20
            out.append(v / self.LSB_PER_G)
        return np.array(out)

    def read_up(self, n: int = 200, interval_s: float = 0.008) -> np.ndarray:
        """Average of n readings (~1.6 s at 125 Hz): the up direction in sensor axes, in g."""
        acc = np.zeros(3)
        for _ in range(n):
            acc += self.read_g()
            time.sleep(interval_s)
        return acc / n

    def close(self) -> None:
        self.spi.close()


def open_imu(kind: str = "adxl355", bus: int | None = None):
    """The level sensor named on the command line: adxl355 (SPI bus 0) or icm42688 (I2C bus 1)."""
    if kind == "adxl355":
        return ADXL355(bus=0 if bus is None else bus)
    if kind == "icm42688":
        return ICM42688(bus=1 if bus is None else bus)
    raise ValueError(f"unknown IMU {kind!r}")


class SimulatedIMU:
    """Returns a fixed (or settable) reading, for simulation and tests."""

    def __init__(self, reading: np.ndarray):
        self.reading = np.asarray(reading, float)

    def read_up(self, n: int = 200, interval_s: float = 0.0) -> np.ndarray:
        return self.reading.copy()

    def close(self) -> None:
        pass
