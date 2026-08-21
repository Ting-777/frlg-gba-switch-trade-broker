from __future__ import annotations

import pytest

from broker.errors import RecoveryRequired
from broker.journal import JournalState, JournalStore, NEXT_STATE, TERMINAL_STATES


@pytest.mark.parametrize(
    "restart_state",
    [state for state in JournalState if state not in TERMINAL_STATES],
)
def test_restart_from_every_nonterminal_state_blocks(tmp_path, mons, restart_state) -> None:
    path = tmp_path / restart_state.value / "journal.json"
    store = JournalStore(path)
    record = store.create(mons[2])
    while record.state_enum != restart_state:
        next_state = NEXT_STATE[record.state_enum]
        kwargs = {}
        if next_state is JournalState.SWITCH_B_CAPTURED:
            kwargs["pokemon"] = {"B": mons[1].sha256}
        if next_state is JournalState.GBA_A_CAPTURED:
            kwargs["pokemon"] = {"A": mons[0].sha256}
        record = store.transition(record, next_state, note="test setup", **kwargs)
    with pytest.raises(RecoveryRequired):
        JournalStore(path).require_new_transaction()
    assert store.load().state_enum is JournalState.RECOVERY_REQUIRED

