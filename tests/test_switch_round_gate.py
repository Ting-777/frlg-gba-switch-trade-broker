from __future__ import annotations

from types import SimpleNamespace

from broker.switch.upstream_driver import _engine_class


class FakeMon:
    def __init__(self, raw: bytes):
        self.raw = bytes(raw)


class FakeBaseEngine:
    def __init__(self, party, **_options):
        self.party = list(party)
        self.round = 0
        self.commits = 0
        self.received_mons = []
        self.requests = []
        self._party600 = b""
        self._party_blocks = []

    def _on_req(self, reqtype):
        self.requests.append(reqtype)

    def _commit(self):
        self.commits += 1
        self.round += 1

    def tick(self):
        return [0] * 7


def test_second_round_party_request_waits_for_new_offer() -> None:
    trade = SimpleNamespace(TradeEngine=FakeBaseEngine, REQ_SIZE={7: 200})
    mon = SimpleNamespace(
        Mon=FakeMon,
        build_player_party=lambda party: b"".join(item.raw for item in party),
        party_blocks=lambda party: [party[index : index + 200] for index in range(0, 600, 200)],
    )
    engine_type = _engine_class(trade, mon)
    placeholder = b"P" * 100
    a_mon = b"A" * 100
    engine = engine_type(placeholder, log=lambda *_args: None)

    engine._commit()
    assert engine.round == 1
    assert not engine.broker_gate_open

    engine._on_req(7)
    assert engine.requests == []
    assert engine.broker_pending_req == 7

    engine.set_second_offer(a_mon)
    engine.tick()
    assert engine.party[1].raw == a_mon
    assert engine.requests == [7]
    assert engine.broker_pending_req is None
