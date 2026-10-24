# Third-party
import pytest

# Local application
from app.management.runtime_settings.registry import REGISTRY, REGISTRY_LIST, validate_value


def test_keys_are_unique_and_prefix_matches_category():
    assert len(REGISTRY) == len(REGISTRY_LIST)
    for d in REGISTRY_LIST:
        assert d.key.split(".")[0] == d.category


def test_every_default_is_valid_and_inside_its_range():
    for d in REGISTRY_LIST:
        assert validate_value(d, d.default) == d.default
        if d.min is not None and d.max is not None:
            assert d.min <= d.default <= d.max


@pytest.mark.parametrize("value", [True, 3.5, "5", None])
def test_int_setting_rejects_wrong_types(value):
    with pytest.raises(ValueError):
        validate_value(REGISTRY["jobs.retention_days"], value)


def test_range_is_enforced():
    d = REGISTRY["ws.max_connections_per_user"]
    with pytest.raises(ValueError):
        validate_value(d, 0)
    with pytest.raises(ValueError):
        validate_value(d, 51)
    assert validate_value(d, 5) == 5
