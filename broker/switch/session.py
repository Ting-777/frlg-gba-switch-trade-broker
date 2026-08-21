"""Persistent Switch-session driver contract."""

from __future__ import annotations

from typing import Protocol

from ..endpoints import TradeResult
from ..pokemon import Pokemon100


class SwitchSessionDriver(Protocol):
    """Implemented by the separately installed AGPL FRLG LDN bridge integration."""

    def connect(self) -> None: ...
    def wait_for_trade_menu(self) -> None: ...
    def set_offer_mon(self, mon: bytes) -> None: ...
    def trade_once(self) -> tuple[bytes, bytes, bool]: ...
    def close(self) -> None: ...


class SwitchTradeSession:
    """Validate a live driver while keeping one connection for both broker trades."""

    def __init__(self, driver: SwitchSessionDriver):
        self.driver = driver
        self.connected = False
        self._prepared: Pokemon100 | None = None

    def connect(self) -> None:
        if self.connected:
            raise RuntimeError("Switch session is already connected")
        self.driver.connect()
        self.connected = True

    def wait_for_trade_menu(self) -> None:
        if not self.connected:
            raise RuntimeError("Switch session is not connected")
        self.driver.wait_for_trade_menu()

    def prepare_offer(self, offered_mon: Pokemon100) -> None:
        """Stage the offer before the host begins its party exchange.

        The second call opens the paused next round in the same LDN session.  It
        therefore cannot be delayed until ``trade_once``: by then the Switch has
        already requested the party bytes that contain this Pokémon.
        """
        if not self.connected:
            raise RuntimeError("Switch session is not connected")
        offered_mon.refuse_mail()
        self.driver.set_offer_mon(offered_mon.raw)
        self._prepared = offered_mon

    def trade_once(self, offered_mon: Pokemon100) -> TradeResult:
        if not self.connected:
            raise RuntimeError("Switch session is not connected")
        offered_mon.refuse_mail()
        if self._prepared != offered_mon:
            raise RuntimeError("Switch offer must be prepared before waiting for the trade menu")
        offered, received, committed = self.driver.trade_once()
        self._prepared = None
        return TradeResult(Pokemon100(offered), Pokemon100(received), bool(committed))

    def close(self) -> None:
        if self.connected:
            self.driver.close()
            self.connected = False
            self._prepared = None
