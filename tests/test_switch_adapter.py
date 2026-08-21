from __future__ import annotations

from broker.switch.session import SwitchTradeSession


def test_adapter_reuses_one_session_and_changes_offer(mons) -> None:
    a_mon, b_mon, placeholder = mons

    class Driver:
        def __init__(self):
            self.owned = b_mon.raw
            self.offered = b""
            self.connects = 0

        def connect(self):
            self.connects += 1

        def wait_for_trade_menu(self):
            pass

        def set_offer_mon(self, mon):
            self.offered = mon

        def trade_once(self):
            received = self.owned
            self.owned = self.offered
            return self.offered, received, True

        def close(self):
            pass

    driver = Driver()
    session = SwitchTradeSession(driver)
    session.connect()
    first = session.trade_once(placeholder)
    second = session.trade_once(a_mon)
    session.close()
    assert first.received_mon == b_mon
    assert second.received_mon == placeholder
    assert driver.owned == a_mon.raw
    assert driver.connects == 1

