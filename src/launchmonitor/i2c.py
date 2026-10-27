"""Minimal Linux I2C access (no dependencies) via the I2C_RDWR ioctl.

I2C_RDWR doesn't claim the address, so it also works on devices a kernel driver
already owns (the cameras' sensors). `ioctl` is injectable for tests.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
from typing import Callable

I2C_RDWR = 0x0707
I2C_M_RD = 0x0001


class _Msg(ctypes.Structure):
    _fields_ = [("addr", ctypes.c_uint16), ("flags", ctypes.c_uint16), ("len", ctypes.c_uint16), ("buf", ctypes.c_void_p)]


class _RdwrData(ctypes.Structure):
    _fields_ = [("msgs", ctypes.POINTER(_Msg)), ("nmsgs", ctypes.c_uint32)]


class I2CDevice:
    def __init__(self, bus: int, addr: int, reg16: bool = False, ioctl: Callable | None = None):
        self.addr = addr
        self.reg16 = reg16
        self._ioctl = ioctl or fcntl.ioctl
        self._fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR) if ioctl is None else -1

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _reg(self, reg: int) -> bytes:
        return bytes([(reg >> 8) & 0xFF, reg & 0xFF]) if self.reg16 else bytes([reg & 0xFF])

    def _transfer(self, msgs: list[tuple[int, bytes | int]]) -> list[bytes]:
        """msgs: (flags, data to write | length to read). Returns the read buffers."""
        bufs, cmsgs = [], []
        for flags, d in msgs:
            n = d if isinstance(d, int) else len(d)
            buf = (ctypes.c_uint8 * n)(*([] if isinstance(d, int) else d))
            bufs.append((flags, buf))
            cmsgs.append(_Msg(self.addr, flags, n, ctypes.cast(buf, ctypes.c_void_p)))
        arr = (_Msg * len(cmsgs))(*cmsgs)
        self._ioctl(self._fd, I2C_RDWR, _RdwrData(ctypes.cast(arr, ctypes.POINTER(_Msg)), len(cmsgs)))
        return [bytes(b) for f, b in bufs if f & I2C_M_RD]

    def write(self, reg: int, val: int) -> None:
        self._transfer([(0, self._reg(reg) + bytes([val & 0xFF]))])

    def read(self, reg: int, n: int) -> bytes:
        return self._transfer([(0, self._reg(reg)), (I2C_M_RD, n)])[0]
