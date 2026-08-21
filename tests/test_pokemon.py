from __future__ import annotations

import hashlib

import pytest

from broker.errors import InvalidPokemon, MailNotSupported
from broker.pokemon import Pokemon100


def test_exact_size_and_copy() -> None:
    with pytest.raises(InvalidPokemon):
        Pokemon100(b"x" * 99)
    mutable = bytearray(100)
    mon = Pokemon100(mutable)
    mutable[0] = 1
    assert mon.raw[0] == 0


def test_hash_file_and_debug(tmp_path, mons) -> None:
    mon = mons[0]
    path = tmp_path / "a.pk3"
    mon.save(path)
    assert Pokemon100.load(path) == mon
    assert mon.sha256 == hashlib.sha256(mon.raw).hexdigest()
    assert mon.hex_debug(2) == mon.raw[:2].hex() + "…"


def test_checksum_sanity(mons) -> None:
    assert mons[0].checksum_valid
    bad = bytearray(mons[0].raw)
    bad[32] = 1
    assert not Pokemon100(bytes(bad)).checksum_valid


def test_mail_is_explicitly_refused() -> None:
    raw = bytearray(100)
    raw[34:36] = (121).to_bytes(2, "little")
    checksum = sum(
        int.from_bytes(raw[offset : offset + 2], "little") for offset in range(32, 80, 2)
    ) & 0xFFFF
    raw[28:30] = checksum.to_bytes(2, "little")
    mon = Pokemon100(bytes(raw))
    assert mon.holds_mail
    with pytest.raises(MailNotSupported):
        mon.refuse_mail()

