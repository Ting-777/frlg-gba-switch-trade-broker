from __future__ import annotations

import pytest

from broker.pokemon import Pokemon100


@pytest.fixture
def mons() -> tuple[Pokemon100, Pokemon100, Pokemon100]:
    def mon(label: str) -> Pokemon100:
        raw = bytearray(100)
        raw[8] = ord(label)
        return Pokemon100(bytes(raw))

    return mon("A"), mon("B"), mon("P")

