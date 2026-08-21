"""Deterministic in-memory GBA endpoint."""

from __future__ import annotations

from ..endpoints import GbaTradeResult
from ..errors import EndpointError
from ..pokemon import Pokemon100


class MockGbaEndpoint:
    def __init__(
        self,
        owned_mon: Pokemon100,
        *,
        selected_slot: int = 2,
        commit_confirmed: bool = True,
        link_closed: bool = True,
        disconnect: bool = False,
    ):
        self.owned_mon = owned_mon
        self.selected_slot = selected_slot
        self.commit_confirmed = commit_confirmed
        self.link_closed = link_closed
        self.disconnect = disconnect
        self.connected = False
        self.trades = 0

    def connect(self) -> None:
        self.connected = True

    def trade_once(self, offered_mon: Pokemon100) -> GbaTradeResult:
        if not self.connected:
            raise EndpointError("mock GBA is not connected")
        if self.disconnect:
            raise EndpointError("mock GBA unexpectedly disconnected")
        received = self.owned_mon
        if self.commit_confirmed:
            self.owned_mon = offered_mon
        self.trades += 1
        return GbaTradeResult(
            offered_mon=offered_mon,
            received_mon=received,
            commit_confirmed=self.commit_confirmed,
            selected_slot=self.selected_slot,
            link_closed=self.link_closed,
        )

    def abort_if_safe(self) -> bool:
        return self.trades == 0

    def close(self) -> None:
        self.connected = False

