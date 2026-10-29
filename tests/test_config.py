import pytest

from netproof.config import load_settings


def test_default_profile_is_spark_13_low_effort():
    s = load_settings()
    assert s.profile == "spark-1.3" and s.model == "muse-spark-1.3" and s.reasoning_effort == "low"
    assert (s.price_in, s.price_cached, s.price_out) == (1.25, 0.15, 4.25)


def test_spark_open_profile_points_at_baseten():
    s = load_settings("spark-open")
    assert s.base_url == "https://inference.baseten.co/v1" and s.key_env == "BASETEN_API_KEY"


def test_unknown_profile_is_an_error():
    with pytest.raises(KeyError):
        load_settings("no-such-model")
