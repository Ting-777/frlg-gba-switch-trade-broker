"""Deterministic A/B/P escrow coordinator."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from .endpoints import GbaEndpoint, GbaTradeResult, SwitchEndpoint, TradeResult
from .errors import CommitNotConfirmed, EndpointError, PlaceholderMismatch
from .journal import JournalRecord, JournalState, JournalStore, TERMINAL_STATES
from .pokemon import Pokemon100

LOG = logging.getLogger(__name__)
FaultHook = Callable[[str, JournalRecord], None]


@dataclass(frozen=True, slots=True)
class TransactionOutcome:
    transaction_id: str
    gba_mon: Pokemon100
    switch_mon: Pokemon100
    broker_mon: Pokemon100


def _no_fault(_boundary: str, _record: JournalRecord) -> None:
    return


class TradeCoordinator:
    """Coordinate independent endpoint trades; never auto-resume uncertain work."""

    def __init__(
        self,
        *,
        journal: JournalStore,
        gba: GbaEndpoint,
        switch: SwitchEndpoint,
        fault_hook: FaultHook = _no_fault,
    ):
        self.journal = journal
        self.gba = gba
        self.switch = switch
        self.fault_hook = fault_hook

    def execute(self, placeholder: Pokemon100) -> TransactionOutcome:
        placeholder.refuse_mail()
        self.journal.require_new_transaction()
        record = self.journal.create(placeholder)
        gba_connected = False
        switch_connected = False

        try:
            self.switch.connect()
            switch_connected = True
            self.gba.connect()
            gba_connected = True

            record = self.journal.transition(
                record,
                JournalState.SWITCH_STAGE1_STARTED,
                note="starting Switch trade B for placeholder P",
            )
            self.fault_hook("before_switch_stage1", record)
            self.switch.wait_for_trade_menu()
            first = self.switch.trade_once(placeholder)
            self.fault_hook("after_switch1_endpoint_before_persist", record)
            self._validate_result(first, expected_offer=placeholder, endpoint="Switch stage 1")
            b_mon = first.received_mon
            b_mon.refuse_mail()
            self.journal.save_artifact(record, "B", b_mon)
            record = self.journal.transition(
                record,
                JournalState.SWITCH_B_CAPTURED,
                note="Switch commit confirmed; B captured and P transferred",
                pokemon={"B": b_mon.sha256},
                locations={"B": "broker", "P": "switch"},
            )
            record = self.journal.transition(
                record,
                JournalState.PLACEHOLDER_ON_SWITCH,
                note="durably recorded placeholder on Switch",
            )
            self.fault_hook("after_placeholder_on_switch", record)

            record = self.journal.transition(
                record,
                JournalState.GBA_STAGE_STARTED,
                note="starting physical GBA trade A for B",
            )
            self.fault_hook("before_gba_trade", record)
            gba_result = self.gba.trade_once(b_mon)
            self.fault_hook("after_gba_endpoint_before_persist", record)
            self._validate_gba_result(gba_result, expected_offer=b_mon)
            a_mon = gba_result.received_mon
            a_mon.refuse_mail()
            self.journal.save_artifact(record, "A", a_mon)
            record = self.journal.transition(
                record,
                JournalState.GBA_A_CAPTURED,
                note="GBA commit confirmed; selected A captured and B transferred",
                pokemon={"A": a_mon.sha256},
                locations={"A": "broker", "B": "gba"},
                selected_gba_slot=gba_result.selected_slot,
            )
            record = self.journal.transition(
                record,
                JournalState.B_COMMITTED_TO_GBA,
                note="durably recorded B ownership on GBA",
            )
            self.fault_hook("after_b_committed_to_gba", record)

            record = self.journal.transition(
                record,
                JournalState.SWITCH_STAGE2_STARTED,
                note="starting Switch return trade P for A",
            )
            self.fault_hook("before_switch_stage2", record)
            self.switch.wait_for_trade_menu()
            second = self.switch.trade_once(a_mon)
            self.fault_hook("after_switch2_endpoint_before_persist", record)
            self._validate_result(second, expected_offer=a_mon, endpoint="Switch stage 2")
            returned = second.received_mon
            self.journal.save_artifact(record, "P_RETURNED", returned)
            record = self.journal.transition(
                record,
                JournalState.A_COMMITTED_TO_SWITCH,
                note="Switch return commit confirmed; A transferred and candidate P captured",
                locations={"A": "switch", "P": "broker (unverified candidate)", "B": "gba"},
            )
            self.fault_hook("before_placeholder_validation", record)
            if returned != placeholder:
                raise PlaceholderMismatch(
                    "returned placeholder mismatch: "
                    f"expected {placeholder.sha256}, received {returned.sha256}"
                )

            record = self.journal.transition(
                record,
                JournalState.COMPLETE,
                note="placeholder recovered byte-for-byte; A/B/P exchange complete",
                locations={"P": "broker"},
            )
            return TransactionOutcome(record.transaction_id, b_mon, a_mon, returned)
        except Exception as exc:
            self._mark_recovery(record, exc)
            raise
        finally:
            if gba_connected:
                try:
                    self.gba.close()
                except Exception:
                    LOG.exception("GBA endpoint close failed")
            if switch_connected:
                try:
                    self.switch.close()
                except Exception:
                    LOG.exception("Switch endpoint close failed")

    @staticmethod
    def _validate_result(
        result: TradeResult, *, expected_offer: Pokemon100, endpoint: str
    ) -> None:
        if result.offered_mon != expected_offer:
            raise EndpointError(
                f"{endpoint} reported a different offered record: "
                f"expected {expected_offer.sha256}, got {result.offered_mon.sha256}"
            )
        if not result.commit_confirmed:
            raise CommitNotConfirmed(f"{endpoint} did not confirm irreversible commit")

    @classmethod
    def _validate_gba_result(
        cls, result: GbaTradeResult, *, expected_offer: Pokemon100
    ) -> None:
        cls._validate_result(result, expected_offer=expected_offer, endpoint="physical GBA")
        if not 0 <= result.selected_slot <= 5:
            raise EndpointError(f"invalid selected GBA slot {result.selected_slot}")
        if not result.link_closed:
            raise CommitNotConfirmed("GBA trade committed but wired link did not close successfully")

    def _mark_recovery(self, record: JournalRecord, exc: Exception) -> None:
        if record.state_enum in TERMINAL_STATES:
            return
        try:
            self.journal.transition(
                record,
                JournalState.RECOVERY_REQUIRED,
                note="transaction stopped because endpoint outcome may be unsafe or incomplete",
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            LOG.exception("could not persist RECOVERY_REQUIRED after %r", exc)
