from __future__ import annotations

import pytest

from broker.errors import CommitNotConfirmed, EndpointError, PlaceholderMismatch
from broker.gba.mock import MockGbaEndpoint
from broker.journal import JournalState, JournalStore
from broker.switch.mock import MockSwitchEndpoint
from broker.transaction import TradeCoordinator


def test_mock_three_stage_exchange(tmp_path, mons) -> None:
    a_mon, b_mon, placeholder = mons
    gba = MockGbaEndpoint(a_mon, selected_slot=3)
    switch = MockSwitchEndpoint(b_mon)
    store = JournalStore(tmp_path / "journal.json")
    outcome = TradeCoordinator(journal=store, gba=gba, switch=switch).execute(placeholder)
    assert outcome.gba_mon == b_mon
    assert outcome.switch_mon == a_mon
    assert outcome.broker_mon == placeholder
    assert gba.owned_mon == b_mon
    assert switch.owned_mon == a_mon
    assert switch.trades == 2
    assert switch.session_connects == 1
    record = store.load()
    assert record.state_enum is JournalState.COMPLETE
    assert record.pokemon == {"A": a_mon.sha256, "B": b_mon.sha256, "P": placeholder.sha256}
    assert record.locations == {"A": "switch", "B": "gba", "P": "broker"}
    assert record.selected_gba_slot == 3


@pytest.mark.parametrize(
    "boundary",
    [
        "before_switch_stage1",
        "after_switch1_endpoint_before_persist",
        "after_placeholder_on_switch",
        "before_gba_trade",
        "after_gba_endpoint_before_persist",
        "after_b_committed_to_gba",
        "before_switch_stage2",
        "after_switch2_endpoint_before_persist",
        "before_placeholder_validation",
    ],
)
def test_failure_at_each_boundary_requires_recovery(tmp_path, mons, boundary) -> None:
    a_mon, b_mon, placeholder = mons

    def fail_here(name, _record):
        if name == boundary:
            raise RuntimeError(f"injected at {name}")

    store = JournalStore(tmp_path / "journal.json")
    coordinator = TradeCoordinator(
        journal=store,
        gba=MockGbaEndpoint(a_mon),
        switch=MockSwitchEndpoint(b_mon),
        fault_hook=fail_here,
    )
    with pytest.raises(RuntimeError, match="injected"):
        coordinator.execute(placeholder)
    record = store.load()
    assert record.state_enum is JournalState.RECOVERY_REQUIRED
    assert boundary in (record.last_error or "")


def test_unconfirmed_gba_commit_requires_recovery(tmp_path, mons) -> None:
    a_mon, b_mon, placeholder = mons
    store = JournalStore(tmp_path / "journal.json")
    coordinator = TradeCoordinator(
        journal=store,
        gba=MockGbaEndpoint(a_mon, commit_confirmed=False),
        switch=MockSwitchEndpoint(b_mon),
    )
    with pytest.raises(CommitNotConfirmed):
        coordinator.execute(placeholder)
    assert store.load().state_enum is JournalState.RECOVERY_REQUIRED


def test_gba_failure_attempts_safe_abort(tmp_path, mons) -> None:
    a_mon, b_mon, placeholder = mons

    class FailingGba(MockGbaEndpoint):
        def __init__(self):
            super().__init__(a_mon)
            self.abort_calls = 0

        def trade_once(self, offered_mon):
            del offered_mon
            raise EndpointError("wired exchange failed before selection")

        def abort_if_safe(self):
            self.abort_calls += 1
            return True

    gba = FailingGba()
    store = JournalStore(tmp_path / "journal.json")
    coordinator = TradeCoordinator(
        journal=store,
        gba=gba,
        switch=MockSwitchEndpoint(b_mon),
    )
    with pytest.raises(EndpointError, match="wired exchange failed"):
        coordinator.execute(placeholder)
    assert gba.abort_calls == 1
    assert store.load().state_enum is JournalState.RECOVERY_REQUIRED


def test_unexpected_disconnect_requires_recovery(tmp_path, mons) -> None:
    a_mon, b_mon, placeholder = mons
    store = JournalStore(tmp_path / "journal.json")
    coordinator = TradeCoordinator(
        journal=store,
        gba=MockGbaEndpoint(a_mon),
        switch=MockSwitchEndpoint(b_mon, fail_on_call=2),
    )
    with pytest.raises(EndpointError, match="disconnected"):
        coordinator.execute(placeholder)
    assert store.load().state_enum is JournalState.RECOVERY_REQUIRED


def test_placeholder_mismatch_requires_recovery(tmp_path, mons) -> None:
    a_mon, b_mon, placeholder = mons

    class WrongReturnSwitch(MockSwitchEndpoint):
        def trade_once(self, offered_mon):
            result = super().trade_once(offered_mon)
            if self.trades == 2:
                return type(result)(result.offered_mon, b_mon, result.commit_confirmed)
            return result

    store = JournalStore(tmp_path / "journal.json")
    coordinator = TradeCoordinator(
        journal=store,
        gba=MockGbaEndpoint(a_mon),
        switch=WrongReturnSwitch(b_mon),
    )
    with pytest.raises(PlaceholderMismatch):
        coordinator.execute(placeholder)
    record = store.load()
    assert record.state_enum is JournalState.RECOVERY_REQUIRED
    assert "mismatch" in (record.last_error or "")
