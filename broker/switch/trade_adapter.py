"""Loader for an external frlg-ldn-trade-gba-bridge broker driver.

The reviewed upstream currently exposes a monolithic CLI/live loop, not this
pauseable API. A checkout can provide `frlg_broker_driver.py` with a `create_driver`
factory while preserving its AGPL notices. We intentionally do not pretend that
subprocess restarts are one persistent Switch session.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from ..errors import EndpointError
from .session import SwitchTradeSession


def load_external_session(checkout: str | Path, **options: Any) -> SwitchTradeSession:
    checkout_path = Path(checkout).resolve()
    module_path = checkout_path / "frlg_broker_driver.py"
    if not module_path.is_file():
        raise EndpointError(
            f"{module_path} is missing; apply the reviewed broker-session integration to the "
            "pinned frlg-ldn-trade-gba-bridge checkout. The legacy CLI cannot safely pause "
            "between two trades in one session."
        )
    spec = importlib.util.spec_from_file_location("frlg_broker_driver", module_path)
    if spec is None or spec.loader is None:
        raise EndpointError(f"cannot load Switch driver module {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_driver", None)
    if not callable(factory):
        raise EndpointError("frlg_broker_driver.py must export create_driver(**options)")
    return SwitchTradeSession(factory(**options))

