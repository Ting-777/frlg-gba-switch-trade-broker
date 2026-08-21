"""Crash-safe, append-auditable transaction journal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Final
from uuid import UUID, uuid4

from .errors import InvalidTransition, JournalError, RecoveryRequired
from .pokemon import Pokemon100


class JournalState(StrEnum):
    IDLE = "IDLE"
    SWITCH_STAGE1_STARTED = "SWITCH_STAGE1_STARTED"
    SWITCH_B_CAPTURED = "SWITCH_B_CAPTURED"
    PLACEHOLDER_ON_SWITCH = "PLACEHOLDER_ON_SWITCH"
    GBA_STAGE_STARTED = "GBA_STAGE_STARTED"
    GBA_A_CAPTURED = "GBA_A_CAPTURED"
    B_COMMITTED_TO_GBA = "B_COMMITTED_TO_GBA"
    SWITCH_STAGE2_STARTED = "SWITCH_STAGE2_STARTED"
    A_COMMITTED_TO_SWITCH = "A_COMMITTED_TO_SWITCH"
    COMPLETE = "COMPLETE"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


TERMINAL_STATES: Final = {JournalState.COMPLETE, JournalState.RECOVERY_REQUIRED}
NEXT_STATE: Final = {
    JournalState.IDLE: JournalState.SWITCH_STAGE1_STARTED,
    JournalState.SWITCH_STAGE1_STARTED: JournalState.SWITCH_B_CAPTURED,
    JournalState.SWITCH_B_CAPTURED: JournalState.PLACEHOLDER_ON_SWITCH,
    JournalState.PLACEHOLDER_ON_SWITCH: JournalState.GBA_STAGE_STARTED,
    JournalState.GBA_STAGE_STARTED: JournalState.GBA_A_CAPTURED,
    JournalState.GBA_A_CAPTURED: JournalState.B_COMMITTED_TO_GBA,
    JournalState.B_COMMITTED_TO_GBA: JournalState.SWITCH_STAGE2_STARTED,
    JournalState.SWITCH_STAGE2_STARTED: JournalState.A_COMMITTED_TO_SWITCH,
    JournalState.A_COMMITTED_TO_SWITCH: JournalState.COMPLETE,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class HistoryEntry:
    sequence: int
    state: str
    at: str
    note: str


@dataclass(slots=True)
class JournalRecord:
    schema_version: int
    transaction_id: str
    state: str
    sequence: int
    created_at: str
    updated_at: str
    pokemon: dict[str, str | None]
    locations: dict[str, str]
    selected_gba_slot: int | None = None
    last_error: str | None = None
    history: list[HistoryEntry] = field(default_factory=list)

    @property
    def state_enum(self) -> JournalState:
        return JournalState(self.state)

    def as_json_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["history"] = [asdict(entry) for entry in self.history]
        return data

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "JournalRecord":
        try:
            history = [HistoryEntry(**entry) for entry in data.get("history", [])]
            record = cls(**{**data, "history": history})
            UUID(record.transaction_id)
            record.state_enum
            if record.schema_version != 1:
                raise JournalError(f"unsupported journal schema {record.schema_version}")
            if record.sequence < 0:
                raise JournalError("negative journal sequence")
            return record
        except (KeyError, TypeError, ValueError) as exc:
            raise JournalError(f"invalid transaction journal: {exc}") from exc


class JournalStore:
    """One active transaction, persisted by fsync + atomic same-directory rename."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.artifacts_dir = self.path.parent / "artifacts"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> JournalRecord:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JournalError(f"cannot read journal {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise JournalError("journal root must be an object")
        return JournalRecord.from_json_dict(data)

    def create(self, placeholder: Pokemon100) -> JournalRecord:
        if self.exists():
            old = self.load()
            raise RecoveryRequired(
                f"journal already exists in {old.state}; archive it before a new transaction"
            )
        now = _now()
        txid = str(uuid4())
        record = JournalRecord(
            schema_version=1,
            transaction_id=txid,
            state=JournalState.IDLE.value,
            sequence=0,
            created_at=now,
            updated_at=now,
            pokemon={"A": None, "B": None, "P": placeholder.sha256},
            locations={"A": "gba (unobserved)", "B": "switch (unobserved)", "P": "broker"},
            history=[HistoryEntry(0, JournalState.IDLE.value, now, "transaction created")],
        )
        self.save_artifact(record, "P", placeholder)
        self._write(record)
        return record

    def transition(
        self,
        record: JournalRecord,
        new_state: JournalState,
        *,
        note: str,
        pokemon: dict[str, str | None] | None = None,
        locations: dict[str, str] | None = None,
        selected_gba_slot: int | None = None,
        error: str | None = None,
    ) -> JournalRecord:
        current = record.state_enum
        if new_state is not JournalState.RECOVERY_REQUIRED and NEXT_STATE.get(current) != new_state:
            raise InvalidTransition(f"cannot transition {current.value} -> {new_state.value}")
        if current in TERMINAL_STATES:
            raise InvalidTransition(f"terminal journal state {current.value} cannot transition")

        record.sequence += 1
        record.state = new_state.value
        record.updated_at = _now()
        if pokemon:
            for key, value in pokemon.items():
                if key not in record.pokemon:
                    raise JournalError(f"unknown Pokémon label {key}")
                previous = record.pokemon[key]
                if previous is not None and value != previous:
                    raise JournalError(f"hash for {key} is immutable")
                record.pokemon[key] = value
        if locations:
            record.locations.update(locations)
        if selected_gba_slot is not None:
            if not 0 <= selected_gba_slot <= 5:
                raise JournalError("GBA selected slot must be 0..5")
            record.selected_gba_slot = selected_gba_slot
        record.last_error = error
        record.history.append(
            HistoryEntry(record.sequence, new_state.value, record.updated_at, note)
        )
        self._write(record)
        return record

    def require_new_transaction(self) -> None:
        if not self.exists():
            return
        record = self.load()
        if record.state_enum not in TERMINAL_STATES:
            self.transition(
                record,
                JournalState.RECOVERY_REQUIRED,
                note="incomplete transaction detected on process start",
                error=f"restart detected while journal was {record.state}",
            )
        raise RecoveryRequired(
            f"journal {self.path} is {self.load().state}; archive it before starting again"
        )

    def save_artifact(self, record: JournalRecord, label: str, mon: Pokemon100) -> Path:
        if label not in {"A", "B", "P", "P_RETURNED"}:
            raise JournalError(f"invalid artifact label {label}")
        txdir = self.artifacts_dir / record.transaction_id
        txdir.mkdir(parents=True, exist_ok=True)
        path = txdir / f"{label}-{mon.sha256}.pk3"
        self._atomic_bytes(path, mon.raw)
        return path

    def _write(self, record: JournalRecord) -> None:
        payload = (
            json.dumps(record.as_json_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        self._atomic_bytes(self.path, payload)

    @staticmethod
    def _atomic_bytes(path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as handle:
                temp_name = handle.name
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            temp_name = None
            dir_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError as exc:
            raise JournalError(f"atomic write failed for {path}: {exc}") from exc
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

