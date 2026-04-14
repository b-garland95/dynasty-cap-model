"""Named model variant configuration for Phase 2 forecasting."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.utils.config import load_league_config


@dataclass
class ModelVariantConfig:
    name: str
    extra_features: list[str] = field(default_factory=list)
    stage2_alpha: float = 1.0


def load_variant_config(variant_name: str, config_path: str | None = None) -> ModelVariantConfig:
    """Load a named variant from the ``phase2_variants`` block in league_config.yaml.

    Raises
    ------
    KeyError
        If ``variant_name`` is not registered.
    """
    config = load_league_config(config_path)
    variants = config.get("phase2_variants", {})
    if variant_name not in variants:
        raise KeyError(
            f"Unknown phase2 variant {variant_name!r}. "
            f"Registered variants: {sorted(variants)}"
        )
    spec = variants[variant_name]
    return ModelVariantConfig(
        name=variant_name,
        extra_features=list(spec.get("extra_features", [])),
        stage2_alpha=float(spec.get("stage2_alpha", 1.0)),
    )


def list_variants(config_path: str | None = None) -> list[str]:
    """Return all registered variant names from league_config.yaml."""
    config = load_league_config(config_path)
    return list(config.get("phase2_variants", {}).keys())
