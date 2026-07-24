"""Connector auto-discovery loader (Engineering Design §3).

Scans this package's modules for ``BaseConnector`` subclasses at import time
so adding a new source is a new file under ``connectors/``, never an
``if platform == "x"`` branch anywhere in the codebase.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

from brandpulse.connectors.base import BaseConnector


def discover_connectors(package: ModuleType | None = None) -> dict[str, type[BaseConnector]]:
    """Return every concrete ``BaseConnector`` subclass found under ``package``.

    Defaults to scanning this package (``brandpulse.connectors``) — real
    connectors are discovered with zero manual registration by dropping a new
    module in this directory. Accepts an explicit ``package`` so tests can
    point discovery at a package of stub connectors instead, without those
    stubs ever needing to live under ``connectors/`` themselves.

    Keyed by the class's ``name`` attribute if set as a class-level default,
    else by class name. Abstract subclasses (partial implementations) are
    skipped.
    """
    discovered: dict[str, type[BaseConnector]] = {}
    package = package or importlib.import_module(__name__)

    for module_info in pkgutil.iter_modules(package.__path__, prefix=f"{package.__name__}."):
        if module_info.name == package.__name__:
            continue
        module = importlib.import_module(module_info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseConnector)
                and obj is not BaseConnector
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                key = getattr(obj, "name", None) or obj.__name__
                discovered[key] = obj

    return discovered
