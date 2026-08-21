"""Load the persistent frlg-ldn-trade-gba-bridge session driver."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from ..errors import EndpointError
from .session import SwitchTradeSession
from .upstream_driver import create_driver as create_builtin_driver


def load_external_session(checkout: str | Path, **options: Any) -> SwitchTradeSession:
    checkout_path = Path(checkout).resolve()
    module_path = checkout_path / "frlg_broker_driver.py"
    if not module_path.is_file():
        return SwitchTradeSession(create_builtin_driver(checkout=checkout_path, **options))
    spec = importlib.util.spec_from_file_location("frlg_broker_driver", module_path)
    if spec is None or spec.loader is None:
        raise EndpointError(f"cannot load Switch driver module {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, "create_driver", None)
    if not callable(factory):
        raise EndpointError("frlg_broker_driver.py must export create_driver(**options)")
    return SwitchTradeSession(factory(**options))
