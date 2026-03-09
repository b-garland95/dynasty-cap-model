from src.utils.config import load_league_config


def test_load_league_config_default_path():
    config = load_league_config()
    assert config["league"]["teams"] == 10
    assert config["cap"]["annual_inflation"] == 0.10
    assert config["cap"]["discount_rate"] == 0.25
