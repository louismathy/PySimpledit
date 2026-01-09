                     
from .base import BaseEffect, EffectConfig
from .registry import build_chain
from . import brightness, bw, contrast, invert, mirror, sepia

def apply_chain_qimage(img, configs):
                                                   
    from dataclasses import asdict
    out = img
                                                       
    cfg_objs = []
    for cfg in configs or []:
        if isinstance(cfg, dict):
            cfg_objs.append(EffectConfig(**cfg))
        else:
            cfg_objs.append(cfg)

    chain = build_chain(cfg_objs)
    for eff in chain:
        out = eff.apply_qimage(out)
    return out

__all__ = ["BaseEffect", "EffectConfig", "apply_chain_qimage", "build_chain"]
