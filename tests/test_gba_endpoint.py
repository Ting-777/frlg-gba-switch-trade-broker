from __future__ import annotations

from uuid import UUID

from broker.gba.gb_link import GbLinkEndpoint
from broker.gba.protocol import Frame, FrameDecoder, MessageType


class RetryTransport:
    def __init__(self):
        self.decoder = FrameDecoder()
        self.pending = bytearray()
        self.writes: list[Frame] = []
        self.response_sequence = 0
        self.capability_attempts = 0

    def open(self):
        pass

    def close(self):
        pass

    def write(self, data: bytes):
        frame = self.decoder.feed(data)[0]
        self.writes.append(frame)
        if frame.message_type is MessageType.HELLO:
            self._reply(frame.transaction_id, MessageType.HELLO)
        elif frame.message_type is MessageType.GET_CAPABILITIES:
            self.capability_attempts += 1
            if self.capability_attempts == 2:
                self._reply(frame.transaction_id, MessageType.CAPABILITIES, b"\x3f\x00\x00\x00")

    def _reply(self, txid: UUID, message_type: MessageType, payload: bytes = b""):
        self.response_sequence += 1
        self.pending.extend(Frame(message_type, txid, self.response_sequence, payload).encode())

    def read(self, size: int, timeout: float) -> bytes:
        del timeout
        data = bytes(self.pending[:size])
        del self.pending[:size]
        return data


def test_command_retry_reuses_the_same_sequence_and_bytes() -> None:
    transport = RetryTransport()
    endpoint = GbLinkEndpoint(transport, timeout=0.05, request_retry_interval=0.001)
    endpoint.connect()

    requests = [frame for frame in transport.writes if frame.message_type is MessageType.GET_CAPABILITIES]
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert requests[0].sequence == 2


def test_async_event_is_kept_while_waiting_for_command_ack() -> None:
    transport = RetryTransport()
    endpoint = GbLinkEndpoint(transport, timeout=0.05)
    endpoint._connected = True
    transport._reply(endpoint._txid, MessageType.TRADE_SESSION_STARTED)
    transport._reply(endpoint._txid, MessageType.OFFER_READY, b"ready")

    ready = endpoint._wait_for({MessageType.OFFER_READY})
    started = endpoint._wait_for({MessageType.TRADE_SESSION_STARTED})

    assert ready.payload == b"ready"
    assert started.message_type is MessageType.TRADE_SESSION_STARTED
