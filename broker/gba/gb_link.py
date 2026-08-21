"""GB-Link endpoint over the framed v1 broker protocol.

Real commit signaling remains hardware-validation-required. This adapter refuses
missing, replayed, contradictory, or timed-out evidence.
"""

from __future__ import annotations

import hashlib
import time
from uuid import uuid4

from ..endpoints import GbaTradeResult
from ..errors import CommitNotConfirmed, EndpointError, ProtocolError
from ..pokemon import Pokemon100
from .protocol import Frame, FrameDecoder, MessageType, ReplayWindow
from .serial import ByteTransport


class _ReceiveTimeout(EndpointError):
    pass


class GbLinkEndpoint:
    def __init__(
        self,
        transport: ByteTransport,
        *,
        timeout: float = 120.0,
        request_retry_interval: float = 2.0,
        offer_slot: int = 0,
    ):
        if not 0 <= offer_slot <= 5:
            raise ValueError("offer_slot must be 0..5")
        self.transport = transport
        self.timeout = timeout
        self.request_retry_interval = request_retry_interval
        self.offer_slot = offer_slot
        self._decoder = FrameDecoder()
        self._replay = ReplayWindow()
        self._inbox: list[Frame] = []
        self._txid = uuid4()
        self._out_sequence = 0
        self._connected = False

    def connect(self) -> None:
        self.transport.open()
        self._connected = True
        try:
            self._request(
                MessageType.HELLO, b"frlg-trade-broker/0.1", {MessageType.HELLO}
            )
            capabilities = self._request(
                MessageType.GET_CAPABILITIES, b"", {MessageType.CAPABILITIES}
            )
        except Exception:
            self.transport.close()
            self._connected = False
            raise
        if len(capabilities.payload) != 4:
            raise ProtocolError("CAPABILITIES payload must be u32")
        required = 0b0011_1111  # export party/mon, inject, abort, commit, close
        value = int.from_bytes(capabilities.payload, "little")
        if value & required != required:
            raise EndpointError(
                f"GB-Link broker capabilities 0x{value:08x} lack required 0x{required:08x}"
            )

    def trade_once(self, offered_mon: Pokemon100) -> GbaTradeResult:
        if not self._connected:
            raise EndpointError("GB-Link endpoint is not connected")
        offered_mon.refuse_mail()
        ready = self._request(
            MessageType.SET_OFFER_MON,
            bytes([self.offer_slot]) + offered_mon.raw,
            {MessageType.OFFER_READY},
        )
        expected_ready = bytes([self.offer_slot]) + bytes.fromhex(offered_mon.sha256)
        if ready.payload != expected_ready:
            raise ProtocolError("OFFER_READY slot/hash does not match requested record")

        self._wait_for({MessageType.TRADE_SESSION_STARTED})
        party = self._wait_for({MessageType.PARTNER_PARTY})
        if len(party.payload) != 600:
            raise ProtocolError("PARTNER_PARTY must be exactly 600 bytes")
        slot_frame = self._wait_for({MessageType.PARTNER_SELECTED_SLOT})
        if len(slot_frame.payload) != 1 or slot_frame.payload[0] > 5:
            raise ProtocolError("PARTNER_SELECTED_SLOT must be one byte in 0..5")
        selected_slot = slot_frame.payload[0]
        mon_frame = self._wait_for({MessageType.PARTNER_SELECTED_MON})
        selected = Pokemon100(mon_frame.payload)
        party_slice = party.payload[selected_slot * 100 : (selected_slot + 1) * 100]
        if selected.raw != party_slice:
            raise ProtocolError("selected-mon event contradicts captured partner party")

        committed = self._wait_for(
            {MessageType.TRADE_COMMITTED, MessageType.TRADE_ABORTED, MessageType.ERROR}
        )
        if committed.message_type is not MessageType.TRADE_COMMITTED:
            raise CommitNotConfirmed(f"GBA trade ended with {committed.message_type.name}")
        expected_commit = hashlib.sha256(offered_mon.raw).digest() + hashlib.sha256(selected.raw).digest()
        if committed.payload != expected_commit:
            raise ProtocolError("TRADE_COMMITTED hashes do not match offered/selected records")

        closed = self._wait_for({MessageType.TRADE_LINK_CLOSED, MessageType.ERROR})
        link_closed = closed.message_type is MessageType.TRADE_LINK_CLOSED and closed.payload == b"\x00"
        return GbaTradeResult(offered_mon, selected, True, selected_slot, link_closed)

    def abort_if_safe(self) -> bool:
        if not self._connected:
            return True
        result = self._request(
            MessageType.ABORT_IF_SAFE,
            b"",
            {MessageType.TRADE_ABORTED, MessageType.ERROR},
        )
        return result.message_type is MessageType.TRADE_ABORTED

    def close(self) -> None:
        self.transport.close()
        self._connected = False

    def _send(self, message_type: MessageType, payload: bytes = b"") -> None:
        self._out_sequence += 1
        self.transport.write(Frame(message_type, self._txid, self._out_sequence, payload).encode())

    def _request(
        self, message_type: MessageType, payload: bytes, wanted: set[MessageType]
    ) -> Frame:
        """Retry a command byte-for-byte so firmware can replay its cached ACK."""
        self._out_sequence += 1
        encoded = Frame(message_type, self._txid, self._out_sequence, payload).encode()
        deadline = time.monotonic() + self.timeout
        while True:
            self.transport.write(encoded)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return self._wait_for(
                    wanted, timeout=min(self.request_retry_interval, remaining)
                )
            except _ReceiveTimeout:
                continue
        names = ", ".join(sorted(item.name for item in wanted))
        raise EndpointError(f"timeout waiting for retried GB-Link response(s): {names}")

    def _wait_for(self, wanted: set[MessageType], *, timeout: float | None = None) -> Frame:
        wait_time = self.timeout if timeout is None else timeout
        deadline = time.monotonic() + wait_time
        while time.monotonic() < deadline:
            queued = self._take_queued(wanted)
            if queued is not None:
                return queued
            data = self.transport.read(512, min(0.25, max(0.0, deadline - time.monotonic())))
            if not data:
                continue
            for frame in self._decoder.feed(data):
                if frame.transaction_id != self._txid:
                    raise ProtocolError("event transaction id does not match active transaction")
                self._replay.accept(frame)
                self._inbox.append(frame)
            queued = self._take_queued(wanted)
            if queued is not None:
                return queued
        names = ", ".join(sorted(item.name for item in wanted))
        raise _ReceiveTimeout(f"timeout waiting for GB-Link event(s): {names}")

    def _take_queued(self, wanted: set[MessageType]) -> Frame | None:
        for index, frame in enumerate(self._inbox):
            if frame.message_type in wanted:
                return self._inbox.pop(index)
            if frame.message_type is MessageType.ERROR:
                self._inbox.pop(index)
                raise EndpointError(f"GB-Link error: {frame.payload!r}")
        return None
