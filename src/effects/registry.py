from __future__ import annotations
from typing import Dict, Type, Iterable, List
from .base import BaseEffect, EffectConfig

                                      
_EFFECTS: Dict[str, Type[BaseEffect]] = {}

def register_effect(cls: Type[BaseEffect]) -> Type[BaseEffect]:
                                                              
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
                                                    
    chain: List[BaseEffect] = []
    for cfg in configs or []:
        cls = get_effect_cls(cfg.type)
        chain.append(cls.from_config(cfg))
    return chain
