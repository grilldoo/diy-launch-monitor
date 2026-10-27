"""Accelerometer for automatic levelling (ICM-42688-P on the Pi's I2C bus 1).

At rest an accelerometer measures +1 g pointing *up* (the reaction to gravity), so the
normalised average reading is the "up" direction in the IMU's own axes. calibration.py
turns that into "up" in the cameras' frame.

UNVERIFIED on hardware: register map from the ICM-42688-P datasheet (bank 0):
WHO_AM_I 0x75 = 0x47, PWR_MGMT0 0x4E, ACCEL_CONFIG0 0x50, ACCEL_DATA_X1 0x1F
(big-endian X, Y, Z), +-2 g full scale = 16384 LSB/g.
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


class SimulatedIMU:
    """Returns a fixed (or settable) reading, for simulation and tests."""

    def __init__(self, reading: np.ndarray):
        self.reading = np.asarray(reading, float)

    def read_up(self, n: int = 200, interval_s: float = 0.0) -> np.ndarray:
        return self.reading.copy()

    def close(self) -> None:
        pass
