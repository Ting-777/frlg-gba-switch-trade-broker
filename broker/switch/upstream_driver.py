"""Pauseable two-round driver for the pinned FRLG LDN bridge.

The upstream live loop remains the owner of transport, Pia and link-state
timing.  This module injects a small ``TradeEngine`` subclass that withholds the
second round's 200-byte party response until the broker has staged Pokémon A.
"""

from __future__ import annotations

from argparse import Namespace
import importlib
import importlib.util
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
from types import ModuleType
from typing import Any, Callable

from ..errors import EndpointError


PINNED_SWITCH_COMMIT = "d1299e124d1ebe702b447e5c9d70501ed57683e6"


def validate_runtime_dependencies() -> None:
    required = {"Crypto": "pycryptodome", "ldn": "ldn", "trio": "trio", "zstandard": "zstandard"}
    missing = [package for module, package in required.items() if importlib.util.find_spec(module) is None]
    if missing:
        raise EndpointError(
            "missing Switch bridge dependencies: "
            + ", ".join(missing)
            + "; install this project with pip install -e '.[hardware]'"
        )


def validate_checkout(checkout: str | Path) -> Path:
    checkout = Path(checkout).resolve()
    required = (checkout / "frlgtrade.py", checkout / "frlgsim" / "trade.py")
    if not all(path.is_file() for path in required):
        raise EndpointError(f"{checkout} is not a frlg-ldn-trade-gba-bridge checkout")
    try:
        commit = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise EndpointError(f"cannot identify Switch bridge commit in {checkout}") from exc
    if commit != PINNED_SWITCH_COMMIT:
        raise EndpointError(
            f"Switch bridge must be pinned to {PINNED_SWITCH_COMMIT}; got {commit}"
        )
    return checkout


def _load_upstream(checkout: Path) -> tuple[ModuleType, ModuleType, ModuleType]:
    checkout = validate_checkout(checkout)
    validate_runtime_dependencies()
    checkout_text = str(checkout)
    if checkout_text not in sys.path:
        sys.path.insert(0, checkout_text)
    try:
        frlgtrade = importlib.import_module("frlgtrade")
        trade = importlib.import_module("frlgsim.trade")
        mon = importlib.import_module("frlgsim.mon")
    except Exception as exc:  # optional native LDN dependencies can fail here
        raise EndpointError(f"cannot import the Switch bridge from {checkout}: {exc}") from exc
    return frlgtrade, trade, mon


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float,
    failure: Callable[[], BaseException | None],
    description: str,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        error = failure()
        if error is not None:
            raise EndpointError(f"Switch live session failed while {description}: {error}") from error
        if predicate():
            return
        time.sleep(0.02)
    raise EndpointError(f"timed out after {timeout:.0f}s while {description}")


def _engine_class(trade_module: ModuleType, mon_module: ModuleType):
    class BrokerTradeEngine(trade_module.TradeEngine):
        """TradeEngine that can park between the two menu exchanges."""

        def __init__(self, initial_mon: bytes, *, log: Any):
            mon = mon_module.Mon(bytes(initial_mon))
            super().__init__(
                [mon, mon],
                trade_slot=0,
                trades=2,
                offered_slots=[0, 1],
                mpid=1,
                trust_pia=False,
                log=log,
            )
            self.broker_gate_open = True
            self.broker_pending_req: int | None = None

        def _on_req(self, reqtype):
            size = trade_module.REQ_SIZE.get(reqtype, 200)
            if self.round == 1 and size == 200 and not self.broker_gate_open:
                self.broker_pending_req = reqtype
                return
            return super()._on_req(reqtype)

        def _commit(self):
            before = self.commits
            result = super()._commit()
            if self.commits > before and self.round == 1:
                # _arm_next_round has rebuilt party bytes already. Close the
                # gate before the next Sim tick can answer a party pull.
                self.broker_gate_open = False
            return result

        def set_second_offer(self, raw: bytes) -> None:
            if self.round != 1 or self.commits != 1:
                raise EndpointError("the second Switch offer can only be staged after trade 1 commits")
            self.party[1] = mon_module.Mon(bytes(raw))
            self._party600 = mon_module.build_player_party(self.party)
            self._party_blocks = mon_module.party_blocks(self._party600)
            self.broker_gate_open = True

        def tick(self):
            if self.broker_gate_open and self.broker_pending_req is not None:
                reqtype = self.broker_pending_req
                self.broker_pending_req = None
                super()._on_req(reqtype)
            return super().tick()

    return BrokerTradeEngine


class LiveSwitchDriver:
    def __init__(self, *, checkout: str | Path, **options: Any):
        self.checkout = Path(checkout).resolve()
        self.options = options
        self.connected = False
        self.engine: Any = None
        self._frlgtrade: ModuleType | None = None
        self._thread: threading.Thread | None = None
        self._failure: BaseException | None = None
        self._reported = 0
        self._offers: list[bytes] = []
        self._tmp = tempfile.TemporaryDirectory(prefix="frlg-broker-switch-")

    def connect(self) -> None:
        if self.connected:
            raise EndpointError("Switch driver connected twice")
        self.connected = True

    def _failure_value(self) -> BaseException | None:
        return self._failure

    def _start(self, first_offer: bytes) -> None:
        frlgtrade, trade, mon = _load_upstream(self.checkout)
        engine_cls = _engine_class(trade, mon)
        log = frlgtrade._Log(bool(self.options.get("verbose", False)), "  [broker]")
        self.engine = engine_cls(first_offer, log=log)
        args = Namespace(
            capture=self.options.get("capture"),
            comm_id=self.options.get("comm_id", ""),
            compress=bool(self.options.get("compress", False)),
            connect_id=self.options.get("connect_id", ""),
            keys=str(self.options["keys_path"]),
            ot=self.options.get("ot", "BROKER"),
            password=self.options.get("password", ""),
            phy=self.options.get("phy", "phy0"),
            self_id=1,
            trades=2,
            out=str(Path(self._tmp.name) / "received.pk3"),
            out_format="ek3",
            out_size=100,
        )
        original_make_engine = frlgtrade.make_engine

        def run() -> None:
            try:
                frlgtrade.make_engine = lambda _args, _lg: self.engine
                frlgtrade.run_live(args, log)
            except BaseException as exc:  # surfaced synchronously by wait/trade calls
                self._failure = exc
            finally:
                frlgtrade.make_engine = original_make_engine

        self._frlgtrade = frlgtrade
        self._thread = threading.Thread(target=run, name="frlg-switch-live", daemon=True)
        self._thread.start()

    def set_offer_mon(self, mon: bytes) -> None:
        if not self.connected:
            raise EndpointError("Switch driver is not connected")
        raw = bytes(mon)
        if len(raw) != 100:
            raise EndpointError(f"Switch offer must be 100 bytes, got {len(raw)}")
        if self.engine is None:
            self._offers.append(raw)
            self._start(raw)
            return
        self.engine.set_second_offer(raw)
        self._offers.append(raw)

    def wait_for_trade_menu(self) -> None:
        if self.engine is None:
            raise EndpointError("stage the Switch offer before waiting for the menu")
        timeout = float(self.options.get("menu_timeout", 300))
        if self._reported == 0:
            predicate = lambda: bool(self.engine.entry.complete)
            description = "waiting for the first Switch trade menu"
        else:
            predicate = lambda: bool(
                self.engine.commits == 1 and self.engine.broker_gate_open
            )
            description = "opening the second round in the same Switch session"
        _wait_until(
            predicate,
            timeout=timeout,
            failure=self._failure_value,
            description=description,
        )

    def trade_once(self) -> tuple[bytes, bytes, bool]:
        index = self._reported
        if index >= len(self._offers):
            raise EndpointError("no prepared Switch offer")
        _wait_until(
            lambda: self.engine.commits > index,
            timeout=float(self.options.get("trade_timeout", 600)),
            failure=self._failure_value,
            description=f"waiting for Switch trade {index + 1} to commit",
        )
        received = bytes(self.engine.received_mons[index].raw)
        offered = self._offers[index]
        self._reported += 1
        return offered, received, True

    def close(self) -> None:
        if not self.connected:
            return
        self.connected = False
        if self._thread is not None and self._reported == 2:
            self._thread.join(timeout=float(self.options.get("close_timeout", 180)))
            if self._thread.is_alive():
                raise EndpointError(
                    "Switch trade committed, but the host did not finish the cancel/walk-out close "
                    "handshake before the timeout"
                )
        self._tmp.cleanup()


def create_driver(*, checkout: str | Path, **options: Any) -> LiveSwitchDriver:
    return LiveSwitchDriver(checkout=checkout, **options)
