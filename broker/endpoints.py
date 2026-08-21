"""Endpoint contracts; hardware timing remains outside the coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .pokemon import Pokemon100


@dataclass(frozen=True, slots=True)
class TradeResult:
    offered_mon: Pokemon100
    received_mon: Pokemon100
    commit_confirmed: bool


@dataclass(frozen=True, slots=True)
class GbaTradeResult(TradeResult):
    selected_slot: int
    link_closed: bool


class SwitchEndpoint(Protocol):
    def connect(self) -> None: ...
    def wait_for_trade_menu(self) -> None: ...
    def trade_once(self, offered_mon: Pokemon100) -> TradeResult: ...
    def close(self) -> None: ...


class GbaEndpoint(Protocol):
    def connect(self) -> None: ...
    def trade_once(self, offered_mon: Pokemon100) -> GbaTradeResult: ...
    def abort_if_safe(self) -> bool: ...
    def close(self) -> None: ...

