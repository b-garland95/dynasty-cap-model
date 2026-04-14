"""Tests for Phase 2 model variant config loader."""

from __future__ import annotations

import pytest

from src.modeling.variant_config import ModelVariantConfig, list_variants, load_variant_config


def test_baseline_variant_loads():
    cfg = load_variant_config("baseline")
    assert isinstance(cfg, ModelVariantConfig)
    assert cfg.name == "baseline"
    assert cfg.extra_features == []


def test_all_registered_variants_load():
    for name in ["baseline", "v1_rookie_xp", "v2_all_demo", "v3_age_only"]:
        cfg = load_variant_config(name)
        assert cfg.name == name


def test_unknown_variant_raises():
    with pytest.raises(KeyError):
        load_variant_config("nonexistent_variant_xyz")


def test_list_variants_returns_baseline():
    variants = list_variants()
    assert "baseline" in variants


def test_variant_extra_features_are_lists():
    for name in list_variants():
        cfg = load_variant_config(name)
        assert isinstance(cfg.extra_features, list)


def test_v2_all_demo_has_all_three_features():
    cfg = load_variant_config("v2_all_demo")
    assert set(cfg.extra_features) == {"is_rookie", "years_of_experience", "age"}
