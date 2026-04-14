"""Backward-compatible re-exports.

This module was split into:
  - src.modeling.phase2_tv_scorer  (Phase 2 ADP→ESV scoring)
  - src.contracts.phase3_dynasty   (Phase 3 dynasty trajectory application)

Import directly from those modules in new code.
"""

from src.contracts.phase3_dynasty import apply_dynasty_tv_path
from src.modeling.phase2_tv_scorer import (
    build_phase2_tv_inputs,
    build_phase2_tv_inputs_from_frames,
)

__all__ = [
    "apply_dynasty_tv_path",
    "build_phase2_tv_inputs",
    "build_phase2_tv_inputs_from_frames",
]
