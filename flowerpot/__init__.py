"""Parametric, print-ready flower pot generator.

    from flowerpot import PotParams, build_pot, audit

    pot = build_pot(PotParams(pot_style="hexagonal", height=120))
    print(audit(pot))
    pot.export("hex_pot.stl")
"""

from .analysis import Report, audit
from .build import build_pot, build_saucer, lathe
from .params import DRAINAGE_PATTERNS, ParameterError, PotParams, STYLES
from .profile import build_profiles

__all__ = [
    "PotParams", "STYLES", "DRAINAGE_PATTERNS", "ParameterError",
    "build_pot", "build_saucer", "build_profiles", "lathe",
    "audit", "Report",
]
__version__ = "1.0.0"
