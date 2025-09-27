from __future__ import annotations
from typing import Dict, Type, Iterable, List
from .base import BaseEffect, EffectConfig

# Global registry: key -> effect class
_EFFECTS: Dict[str, Type[BaseEffect]] = {}

def register_effect(cls: Type[BaseEffect]) -> Type[BaseEffect]:
    """Decorator to register an effect class under cls.key."""
    key = getattr(cls, "key", None)
    if not key or not isinstance(key, str):
        raise ValueError(f"{cls.__name__} must define a string 'key'")
    _EFFECTS[key] = cls
    return cls

def get_effect_cls(key: str) -> Type[BaseEffect]:
    if key not in _EFFECTS:
        raise KeyError(f"Effect '{key}' is not registered.")
    return _EFFECTS[key]

def build_chain(configs: Iterable[EffectConfig]) -> List[BaseEffect]:
    """Instantiate effects from configs in order."""
    chain: List[BaseEffect] = []
    for cfg in configs or []:
        cls = get_effect_cls(cfg.type)
        chain.append(cls.from_config(cfg))
    return chain
