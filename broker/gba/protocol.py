"""Versioned, CRC-protected GB-Link broker frame codec."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct
from typing import Final
from uuid import UUID
import zlib

from ..errors import ProtocolError

MAGIC: Final = b"FGBR"
VERSION: Final = 1
MAX_PAYLOAD: Final = 4096
HEADER: Final = struct.Struct("<4sBBHI16sI")
CRC: Final = struct.Struct("<I")


class MessageType(IntEnum):
    HELLO = 0x01
    GET_CAPABILITIES = 0x02
    CAPABILITIES = 0x03
    TRADE_SESSION_STARTED = 0x10
    PARTNER_PARTY = 0x11
    PARTNER_SELECTED_SLOT = 0x12
    PARTNER_SELECTED_MON = 0x13
    SET_OFFER_MON = 0x20
    OFFER_READY = 0x21
    TRADE_NEGOTIATION = 0x22
    TRADE_COMMITTED = 0x23
    TRADE_ABORTED = 0x24
    TRADE_LINK_CLOSED = 0x25
    ABORT_IF_SAFE = 0x26
    ERROR = 0x7F


@dataclass(frozen=True, slots=True)
class Frame:
    message_type: MessageType
    transaction_id: UUID
    sequence: int
    payload: bytes = b""
    flags: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", bytes(self.payload))
        if not 0 <= self.sequence <= 0xFFFFFFFF:
            raise ProtocolError("frame sequence does not fit u32")
        if self.flags != 0:
            raise ProtocolError("v1 frame flags must be zero")
        if len(self.payload) > MAX_PAYLOAD:
            raise ProtocolError(f"payload exceeds {MAX_PAYLOAD} bytes")

    def encode(self) -> bytes:
        header = HEADER.pack(
            MAGIC,
            VERSION,
            int(self.message_type),
            self.flags,
            len(self.payload),
            self.transaction_id.bytes,
            self.sequence,
        )
        body = header + self.payload
        return body + CRC.pack(zlib.crc32(body) & 0xFFFFFFFF)


class FrameDecoder:
    """Incrementally parse arbitrary USB chunks without newline assumptions."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer.extend(data)
        frames: list[Frame] = []
        while True:
            magic_at = self._buffer.find(MAGIC)
            if magic_at < 0:
                # Preserve a possible partial magic prefix across reads.
                keep = min(len(self._buffer), len(MAGIC) - 1)
                if keep:
                    del self._buffer[:-keep]
                else:
                    self._buffer.clear()
                break
            if magic_at:
                del self._buffer[:magic_at]
            if len(self._buffer) < HEADER.size:
                break
            magic, version, raw_type, flags, size, txid, sequence = HEADER.unpack_from(self._buffer)
            if magic != MAGIC:
                raise ProtocolError("internal frame resynchronization failure")
            if size > MAX_PAYLOAD:
                del self._buffer[: len(MAGIC)]
                raise ProtocolError(f"declared payload exceeds {MAX_PAYLOAD} bytes")
            total = HEADER.size + size + CRC.size
            if len(self._buffer) < total:
                break
            encoded = bytes(self._buffer[: HEADER.size + size])
            expected_crc = CRC.unpack_from(self._buffer, HEADER.size + size)[0]
            del self._buffer[:total]
            actual_crc = zlib.crc32(encoded) & 0xFFFFFFFF
            if actual_crc != expected_crc:
                raise ProtocolError(
                    f"frame CRC mismatch: expected {expected_crc:08x}, got {actual_crc:08x}"
                )
            if version != VERSION:
                raise ProtocolError(f"unsupported protocol version {version}")
            if flags != 0:
                raise ProtocolError(f"unsupported v1 flags 0x{flags:04x}")
            try:
                message_type = MessageType(raw_type)
            except ValueError as exc:
                raise ProtocolError(f"unknown message type 0x{raw_type:02x}") from exc
            frames.append(
                Frame(message_type, UUID(bytes=txid), sequence, encoded[HEADER.size:], flags)
            )
        return frames


class ReplayWindow:
    """Reject duplicate/decreasing device events per transaction."""

    def __init__(self) -> None:
        self._last: dict[UUID, int] = {}

    def accept(self, frame: Frame) -> None:
        previous = self._last.get(frame.transaction_id)
        if previous is not None and frame.sequence <= previous:
            raise ProtocolError(
                f"replayed/out-of-order frame {frame.sequence}; last accepted was {previous}"
            )
        self._last[frame.transaction_id] = frame.sequence

