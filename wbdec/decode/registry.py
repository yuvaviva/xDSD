"""Adapter registry.

Adapters register themselves at import time via ``@register_adapter``.
``get_adapters_for(label)`` returns a ranked list (in insertion order)
of candidates — the orchestrator picks the first one whose
``is_available()`` returns True.
"""

from __future__ import annotations

from typing import Dict, List, Type

from .base import ProtocolAdapter


_REGISTRY: Dict[str, Type[ProtocolAdapter]] = {}


def register_adapter(cls: Type[ProtocolAdapter]) -> Type[ProtocolAdapter]:
    if cls.name in _REGISTRY and _REGISTRY[cls.name] is not cls:
        raise ValueError(f"adapter name collision: {cls.name}")
    _REGISTRY[cls.name] = cls
    return cls


def all_adapters() -> List[Type[ProtocolAdapter]]:
    return list(_REGISTRY.values())


def get_adapters_for(label: str, demod_hint: str | None = None
                     ) -> List[Type[ProtocolAdapter]]:
    """Return adapter classes (not instances) that declare support for
    ``label`` and — if ``demod_hint`` is provided — match it.
    """
    out: List[Type[ProtocolAdapter]] = []
    for cls in _REGISTRY.values():
        if label not in cls.protocols:
            continue
        if demod_hint is not None and cls.demod_hint != demod_hint:
            continue
        out.append(cls)
    return out


def get_adapter_by_name(name: str) -> Type[ProtocolAdapter] | None:
    return _REGISTRY.get(name)
