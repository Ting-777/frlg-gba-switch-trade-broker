"""Deterministic in-memory Switch endpoint preserving one session."""

from __future__ import annotations

from ..endpoints import TradeResult
from ..errors import EndpointError
from ..pokemon import Pokemon100


class MockSwitchEndpoint:
    def __init__(
        self,
        owned_mon: Pokemon100,
        *,
        fail_on_call: int | None = None,
        commit_on_calls: set[int] | None = None,
    ):
        self.owned_mon = owned_mon
        self.fail_on_call = fail_on_call
        self.commit_on_calls = commit_on_calls
        self.connected = False
        self.trades = 0
        self.session_connects = 0

    def connect(self) -> None:
        if self.connected:
            raise EndpointError("mock Switch session connected twice")
        self.connected = True
        self.session_connects += 1

    def wait_for_trade_menu(self) -> None:
        if not self.connected:
            raise EndpointError("mock Switch is not connected")

    def trade_once(self, offered_mon: Pokemon100) -> TradeResult:
        if not self.connected:
            raise EndpointError("mock Switch is not connected")
        call = self.trades + 1
        if call == self.fail_on_call:
            raise EndpointError(f"mock Switch disconnected during trade {call}")
        received = self.owned_mon
        committed = self.commit_on_calls is None or call in self.commit_on_calls
        if committed:
            self.owned_mon = offered_mon
        self.trades = call
        return TradeResult(offered_mon, received, committed)

    def close(self) -> None:
        self.connected = False

