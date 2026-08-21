"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from .errors import BrokerError, RecoveryRequired
from .gba.gb_link import GbLinkEndpoint
from .gba.mock import MockGbaEndpoint
from .gba.serial import SerialTransport
from .journal import JournalStore
from .pokemon import Pokemon100
from .switch.mock import MockSwitchEndpoint
from .switch.trade_adapter import load_external_session
from .transaction import TradeCoordinator


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


def _demo_mon(label: str) -> Pokemon100:
    if len(label) != 1:
        raise ValueError("demo label must be one character")
    raw = bytearray(100)
    raw[8] = ord(label)
    return Pokemon100(bytes(raw))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="frlg-trade-broker",
        description="Transactional physical GBA FRLG ↔ Switch FRLG trade broker",
    )
    parser.add_argument("--journal", type=Path, default=Path("journal.json"))
    parser.add_argument("--status", action="store_true", help="show journal status; never trade")
    parser.add_argument("--mock-demo", action="store_true", help="run deterministic A/B/P mock swap")
    parser.add_argument("--placeholder", type=Path)
    parser.add_argument("--gba", metavar="DEVICE")
    parser.add_argument("--switch-checkout", type=Path)
    parser.add_argument("--phy", default="phy0")
    parser.add_argument("--keys", type=Path)
    parser.add_argument("--json-logs", action="store_true")
    return parser


def _configure_logging(json_logs: bool) -> None:
    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def _show_status(store: JournalStore) -> int:
    if not store.exists():
        print("No transaction journal exists.")
        return 0
    record = store.load()
    print(json.dumps(record.as_json_dict(), indent=2, ensure_ascii=False, sort_keys=True))
    return 2 if record.state == "RECOVERY_REQUIRED" else 0


def _run_mock(store: JournalStore) -> int:
    a_mon, b_mon, placeholder = (_demo_mon("A"), _demo_mon("B"), _demo_mon("P"))
    gba = MockGbaEndpoint(a_mon, selected_slot=2)
    switch = MockSwitchEndpoint(b_mon)
    print("FRLG GBA <-> Switch Trade Broker (mock demo)")
    outcome = TradeCoordinator(journal=store, gba=gba, switch=switch).execute(placeholder)
    assert gba.owned_mon == b_mon
    assert switch.owned_mon == a_mon
    assert outcome.broker_mon == placeholder
    print(f"GBA=B      {gba.owned_mon.sha256}")
    print(f"Switch=A   {switch.owned_mon.sha256}")
    print(f"Broker=P   {outcome.broker_mon.sha256}")
    print(f"Trade COMPLETE. transaction={outcome.transaction_id}")
    return 0


def _run_real(args: argparse.Namespace, store: JournalStore) -> int:
    missing = [
        name
        for name, value in (
            ("--placeholder", args.placeholder),
            ("--gba", args.gba),
            ("--switch-checkout", args.switch_checkout),
            ("--keys", args.keys),
        )
        if value is None
    ]
    if missing:
        raise BrokerError(f"real mode requires: {', '.join(missing)}")
    placeholder = Pokemon100.load(args.placeholder)
    placeholder.refuse_mail()
    gba = GbLinkEndpoint(SerialTransport(args.gba))
    switch = load_external_session(
        args.switch_checkout, phy=args.phy, keys_path=str(args.keys)
    )
    outcome = TradeCoordinator(journal=store, gba=gba, switch=switch).execute(placeholder)
    print(f"Trade COMPLETE. transaction={outcome.transaction_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.json_logs)
    store = JournalStore(args.journal)
    try:
        if args.status:
            return _show_status(store)
        if args.mock_demo:
            return _run_mock(store)
        return _run_real(args, store)
    except RecoveryRequired as exc:
        print(f"RECOVERY_REQUIRED: {exc}", file=sys.stderr)
        return 2
    except BrokerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

