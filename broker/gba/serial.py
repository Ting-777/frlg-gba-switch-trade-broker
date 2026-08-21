"""Optional pyserial byte transport isolated from protocol/state logic."""

from __future__ import annotations

import time
from typing import Protocol

from ..errors import EndpointError


class ByteTransport(Protocol):
    def open(self) -> None: ...
    def read(self, size: int, timeout: float) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    def close(self) -> None: ...


class SerialTransport:
    _SYNC = b"GB"
    _CHANNEL_COMMAND = 0
    _CHANNEL_DATA = 1
    _CHANNEL_STATUS = 2
    _MAX_OUTER_PAYLOAD = 64

    def __init__(self, device: str, *, baudrate: int = 115200):
        self.device = device
        self.baudrate = baudrate
        self._serial = None
        self._outer_buffer = bytearray()
        self._data_buffer = bytearray()

    def open(self) -> None:
        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:
            raise EndpointError("install the 'serial' extra to use a real GB-Link") from exc
        try:
            self._serial = serial.Serial(self.device, self.baudrate, timeout=0.1)
        except Exception as exc:
            raise EndpointError(f"cannot open GBA adapter {self.device}: {exc}") from exc
        # Reuse GBLink-Firmware's existing CDC-ACM packet layer. Mode 0 is the
        # Gen 3 trade emulator; variant 1 is added by the broker integration so
        # data-channel chunks feed the inner FGBR stream instead of .pk3 upload.
        self._write_outer(self._CHANNEL_COMMAND, b"\x00\x00\x01")

    def read(self, size: int, timeout: float) -> bytes:
        if self._serial is None:
            raise EndpointError("serial transport is not open")
        deadline = time.monotonic() + timeout
        while not self._data_buffer and time.monotonic() < deadline:
            old_timeout = self._serial.timeout
            self._serial.timeout = min(0.1, max(0.0, deadline - time.monotonic()))
            try:
                chunk = bytes(self._serial.read(max(size, 64)))
            finally:
                self._serial.timeout = old_timeout
            if chunk:
                self._feed_outer(chunk)
        result = bytes(self._data_buffer[:size])
        del self._data_buffer[:size]
        return result

    def write(self, data: bytes) -> None:
        if self._serial is None:
            raise EndpointError("serial transport is not open")
        for offset in range(0, len(data), self._MAX_OUTER_PAYLOAD):
            self._write_outer(self._CHANNEL_DATA, data[offset : offset + self._MAX_OUTER_PAYLOAD])

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None

    def _write_outer(self, channel: int, payload: bytes) -> None:
        if self._serial is None:
            raise EndpointError("serial transport is not open")
        if len(payload) > self._MAX_OUTER_PAYLOAD:
            raise EndpointError("GB-Link CDC outer payload exceeds 64 bytes")
        frame = self._SYNC + bytes([channel]) + len(payload).to_bytes(2, "little") + payload
        written = self._serial.write(frame)
        self._serial.flush()
        if written != len(frame):
            raise EndpointError(f"short USB write: {written}/{len(frame)} bytes")

    def _feed_outer(self, data: bytes) -> None:
        self._outer_buffer.extend(data)
        while True:
            sync_at = self._outer_buffer.find(self._SYNC)
            if sync_at < 0:
                if self._outer_buffer[-1:] == self._SYNC[:1]:
                    del self._outer_buffer[:-1]
                else:
                    self._outer_buffer.clear()
                return
            if sync_at:
                del self._outer_buffer[:sync_at]
            if len(self._outer_buffer) < 5:
                return
            channel = self._outer_buffer[2]
            length = int.from_bytes(self._outer_buffer[3:5], "little")
            if length > self._MAX_OUTER_PAYLOAD:
                del self._outer_buffer[:2]
                raise EndpointError(f"invalid GB-Link CDC outer length {length}")
            if len(self._outer_buffer) < 5 + length:
                return
            payload = bytes(self._outer_buffer[5 : 5 + length])
            del self._outer_buffer[: 5 + length]
            if channel == self._CHANNEL_DATA:
                self._data_buffer.extend(payload)
            elif channel not in (self._CHANNEL_COMMAND, self._CHANNEL_STATUS):
                raise EndpointError(f"unknown GB-Link CDC channel {channel}")
