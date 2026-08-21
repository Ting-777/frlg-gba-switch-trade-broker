from __future__ import annotations

from uuid import uuid4

import pytest

from broker.errors import ProtocolError
from broker.gba.protocol import Frame, FrameDecoder, MessageType, ReplayWindow
from broker.gba.serial import SerialTransport


def test_frame_round_trip_across_arbitrary_chunks() -> None:
    txid = uuid4()
    encoded = Frame(MessageType.PARTNER_SELECTED_MON, txid, 7, b"x" * 100).encode()
    decoder = FrameDecoder()
    frames = []
    for byte in encoded:
        frames.extend(decoder.feed(bytes([byte])))
    assert frames == [Frame(MessageType.PARTNER_SELECTED_MON, txid, 7, b"x" * 100)]


def test_noise_resync_and_concatenated_frames() -> None:
    txid = uuid4()
    one = Frame(MessageType.HELLO, txid, 1, b"one")
    two = Frame(MessageType.CAPABILITIES, txid, 2, b"\x3f\x00\x00\x00")
    assert FrameDecoder().feed(b"noise" + one.encode() + two.encode()) == [one, two]


def test_crc_corruption_is_rejected() -> None:
    data = bytearray(Frame(MessageType.HELLO, uuid4(), 1, b"hello").encode())
    data[-5] ^= 0x01
    with pytest.raises(ProtocolError, match="CRC"):
        FrameDecoder().feed(data)


def test_duplicate_and_replayed_events_are_rejected() -> None:
    txid = uuid4()
    window = ReplayWindow()
    window.accept(Frame(MessageType.HELLO, txid, 5))
    with pytest.raises(ProtocolError, match="replayed"):
        window.accept(Frame(MessageType.HELLO, txid, 5))
    with pytest.raises(ProtocolError, match="out-of-order"):
        window.accept(Frame(MessageType.HELLO, txid, 4))


def test_serial_transport_reuses_existing_64_byte_outer_frames() -> None:
    class FakeSerial:
        def __init__(self):
            self.writes = []
            self.timeout = 0.1

        def write(self, data):
            self.writes.append(bytes(data))
            return len(data)

        def flush(self):
            pass

    transport = SerialTransport("unused")
    fake = FakeSerial()
    transport._serial = fake
    transport.write(b"x" * 100)
    assert [len(frame) for frame in fake.writes] == [69, 41]
    assert fake.writes[0][:5] == b"GB\x01\x40\x00"
    assert fake.writes[1][:5] == b"GB\x01\x24\x00"

    outer = b"GB\x01\x03\x00abcGB\x02\x02\x00okGB\x01\x03\x00def"
    transport._feed_outer(outer[:7])
    transport._feed_outer(outer[7:])
    assert bytes(transport._data_buffer) == b"abcdef"
