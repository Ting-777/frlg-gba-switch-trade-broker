from __future__ import annotations

import json

import pytest

from broker.errors import InvalidTransition, JournalError, RecoveryRequired
from broker.journal import JournalState, JournalStore


def test_create_persists_placeholder_and_atomic_json(tmp_path, mons) -> None:
    store = JournalStore(tmp_path / "journal.json")
    record = store.create(mons[2])
    loaded = store.load()
    assert loaded.transaction_id == record.transaction_id
    assert loaded.pokemon["P"] == mons[2].sha256
    artifact = tmp_path / "artifacts" / record.transaction_id / f"P-{mons[2].sha256}.pk3"
    assert artifact.read_bytes() == mons[2].raw
    assert json.loads(store.path.read_text())["state"] == "IDLE"
    assert not list(tmp_path.glob(".journal.json.*"))


def test_transition_graph_and_hash_immutability(tmp_path, mons) -> None:
    store = JournalStore(tmp_path / "journal.json")
    record = store.create(mons[2])
    with pytest.raises(InvalidTransition):
        store.transition(record, JournalState.GBA_STAGE_STARTED, note="skip")
    record = store.transition(record, JournalState.SWITCH_STAGE1_STARTED, note="start")
    record = store.transition(
        record,
        JournalState.SWITCH_B_CAPTURED,
        note="captured",
        pokemon={"B": mons[1].sha256},
    )
    record = store.transition(record, JournalState.PLACEHOLDER_ON_SWITCH, note="placed")
    with pytest.raises(JournalError):
        store.transition(
            record,
            JournalState.GBA_STAGE_STARTED,
            note="mutate hash",
            pokemon={"B": mons[0].sha256},
        )


def test_restart_marks_incomplete_recovery(tmp_path, mons) -> None:
    store = JournalStore(tmp_path / "journal.json")
    record = store.create(mons[2])
    store.transition(record, JournalState.SWITCH_STAGE1_STARTED, note="start")
    with pytest.raises(RecoveryRequired):
        JournalStore(store.path).require_new_transaction()
    assert store.load().state_enum is JournalState.RECOVERY_REQUIRED

