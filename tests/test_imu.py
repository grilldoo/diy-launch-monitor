import numpy as np
import pytest

from launchmonitor.imu import ADXL355


class FakeSPI:
    """Minimal ADXL355 register file behind the SPI protocol: (reg << 1) | 1 reads, reg << 1 writes."""

    def __init__(self, xyz_g):
        self.regs = {0x00: 0xAD, 0x02: 0xED, 0x2C: 0x81, 0x2D: 0x01}
        for i, g in enumerate(xyz_g):
            v = int(round(g * ADXL355.LSB_PER_G)) & 0xFFFFF  # 20-bit two's complement
            self.regs[0x08 + 3 * i] = (v >> 12) & 0xFF
            self.regs[0x09 + 3 * i] = (v >> 4) & 0xFF
            self.regs[0x0A + 3 * i] = (v & 0xF) << 4
        self.writes = []

    def xfer2(self, data):
        reg, rd = data[0] >> 1, data[0] & 1
        if rd:
            return [0] + [self.regs.get(reg + i, 0) for i in range(len(data) - 1)]
        self.writes.append((reg, data[1]))
        self.regs[reg] = data[1]
        return [0, 0]

    def close(self):
        pass


def test_adxl355_reads_signed_20bit_g_and_configures():
    spi = FakeSPI([0.0123, -0.5, 0.99])
    imu = ADXL355(spi=spi)
    assert (0x2D, 0x00) in spi.writes and (0x2C, 0x81) in spi.writes  # measuring at +-2 g
    assert np.allclose(imu.read_g(), [0.0123, -0.5, 0.99], atol=1e-5)


def test_adxl355_wrong_chip_is_an_error():
    spi = FakeSPI([0, 0, 1])
    spi.regs[0x02] = 0x00
    with pytest.raises(RuntimeError):
        ADXL355(spi=spi)
