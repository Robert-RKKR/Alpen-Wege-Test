# Standard library
import math
from uuid import UUID

# Third-party
import pytest

# Local application
from app.explorer.services.continuity import (
    EndPoint, SlotItem, check_continuity, check_structure, connected, distance_m, validate,
)

LAT_M = 1 / 110540            # degrees of latitude per metre
T = 50.0                      # the default threshold
POI_A, POI_B = UUID(int=1), UUID(int=2)


def pt(north_m=0.0, east_m=0.0, poi=None):
    return EndPoint(11.0 + east_m / (111320 * math.cos(math.radians(47.0))), 47.0 + north_m * LAT_M, poi)


def item(slot, start, end, default=True, reverse=False, ref=None, alt_group=None, segment_id=None):
    return SlotItem(ref or f"s{slot}{'d' if default else 'a'}", slot, default, reverse, start, end, alt_group, segment_id)


def kinds(issues):
    return sorted(i.kind for i in issues)


# ------------------------------------------------------------------ connected
def test_two_points_are_connected_when_close_or_at_the_same_poi():
    assert connected(pt(0), pt(49), T)[0] is True
    assert connected(pt(0), pt(51), T)[0] is False
    assert connected(pt(0, poi=POI_A), pt(900, poi=POI_A), T)[0] is True            # the same POI: connected whatever the distance
    assert connected(pt(0, poi=POI_A), pt(10, poi=POI_B), T)[0] is True             # different POIs 10 m apart: the distance decides
    assert connected(pt(0, poi=POI_A), pt(900, poi=POI_B), T)[0] is False
    assert connected(pt(0, poi=POI_A), pt(900), T)[0] is False                      # only one side has a POI: the distance decides
    assert connected(pt(0), pt(900, poi=POI_A), T)[0] is False


def test_opposite_points_have_a_distance_and_do_not_crash():
    far = EndPoint(180.0, -10.0)
    assert connected(EndPoint(0.0, 10.0), far, T)[0] is False
    assert distance_m(EndPoint(0.0, 10.0), far) > 19_000_000
    # a pair on which rounding makes the haversine term exceed 1 by one step: the distance is still half the earth
    assert distance_m(EndPoint(86.5812282599507, 69.51232454868148), EndPoint(86.5812282599507 - 180, -69.51232454868148)) > 19_000_000


def test_the_distance_is_in_metres():
    assert distance_m(pt(0), pt(100)) == pytest.approx(100, rel=0.01)
    assert distance_m(pt(0), pt(0, 100)) == pytest.approx(100, rel=0.01)


# ------------------------------------------------------------------ structure
def test_a_good_list_has_no_structure_problem():
    items = [item(0, pt(0), pt(100)), item(1, pt(100), pt(200)), item(1, pt(100), pt(200), default=False), item(2, pt(200), pt(300))]
    assert check_structure(items, 50) == []
    assert check_structure([], 50) == []                                          # an empty route is allowed


@pytest.mark.parametrize("items,kind", [
    ([item(0, pt(), pt(1)), item(2, pt(), pt(1))], "slot_gap"),
    ([item(1, pt(), pt(1))], "slot_gap"),                                          # does not start at 0
    ([item(0, pt(), pt(1), default=False)], "no_default"),
    ([item(0, pt(), pt(1)), item(0, pt(), pt(1), ref="x")], "multiple_defaults"),
    ([item(0, pt(), pt(1), alt_group=2)], "alt_group_mismatch"),
    ([item(0, pt(), pt(1), segment_id=UUID(int=5)), item(0, pt(), pt(1), default=False, ref="b", segment_id=UUID(int=5))], "duplicate_in_slot"),
])
def test_structure_problems_are_found(items, kind):
    assert kind in kinds(check_structure(items, 50))


def test_too_many_rows():
    items = [item(i, pt(i), pt(i + 1)) for i in range(4)]
    assert kinds(check_structure(items, 3)) == ["too_many_segments"]
    assert check_structure(items, 4) == []


def test_the_same_segment_in_two_different_slots_is_fine():
    sid = UUID(int=9)
    items = [item(0, pt(0), pt(100), segment_id=sid), item(1, pt(100), pt(0), segment_id=sid, reverse=True)]
    assert check_structure(items, 50) == []


# ------------------------------------------------------------------ continuity
def test_a_connected_chain_is_valid():
    items = [item(0, pt(0), pt(100)), item(1, pt(110), pt(300)), item(2, pt(300), pt(500))]
    assert validate(items, T, 50).is_valid


def test_a_gap_is_a_warning_with_slot_and_distance():
    items = [item(0, pt(0), pt(100)), item(1, pt(300), pt(500))]
    result = validate(items, T, 50)
    assert not result.is_valid and result.errors == [] and kinds(result.warnings) == ["gap"]
    issue = result.warnings[0]
    assert issue.slot == 0 and issue.distance_m == pytest.approx(200, rel=0.02) and f"{issue.distance_m:.0f} m" in issue.message


def test_a_reversed_segment_swaps_its_ends():
    forward = [item(0, pt(0), pt(100)), item(1, pt(300), pt(100))]                  # the second one is stored the other way round
    assert kinds(validate(forward, T, 50).warnings) == ["gap"]
    turned = [item(0, pt(0), pt(100)), item(1, pt(300), pt(100), reverse=True)]
    assert validate(turned, T, 50).is_valid
    first_turned = [item(0, pt(0), pt(100), reverse=True), item(1, pt(100), pt(300))]    # walked backwards the first one ends at 0 m, the next starts at 100 m
    assert kinds(validate(first_turned, T, 50).warnings) == ["gap"]
    backwards_ok = [item(0, pt(100), pt(0), reverse=True), item(1, pt(100), pt(300))]    # stored 100 -> 0, walked 0 -> 100, then on from 100
    assert validate(backwards_ok, T, 50).is_valid


def test_the_chain_is_checked_between_the_defaults_only():
    items = [item(0, pt(0), pt(100)), item(1, pt(100), pt(200)), item(1, pt(5000), pt(6000), default=False), item(2, pt(200), pt(300))]
    kinds_found = kinds(validate(items, T, 50).warnings)
    assert kinds_found == ["alternative_end_mismatch", "alternative_start_mismatch"]    # not a gap: the alternative is not on the chain


def test_an_alternative_must_start_and_end_where_the_default_does():
    ok = [item(0, pt(0), pt(100)), item(0, pt(10), pt(90), default=False)]
    assert validate(ok, T, 50).is_valid
    bad_start = [item(0, pt(0), pt(100)), item(0, pt(300), pt(100), default=False)]
    assert kinds(validate(bad_start, T, 50).warnings) == ["alternative_start_mismatch"]
    bad_end = [item(0, pt(0), pt(100)), item(0, pt(0), pt(900), default=False)]
    assert kinds(validate(bad_end, T, 50).warnings) == ["alternative_end_mismatch"]


def test_an_alternative_is_compared_as_walked():
    default = item(0, pt(0), pt(100))
    reversed_alt = item(0, pt(100), pt(0), default=False, reverse=True)           # stored backwards, walked forwards
    assert validate([default, reversed_alt], T, 50).is_valid
    not_reversed = item(0, pt(100), pt(0), default=False)
    assert len(validate([default, not_reversed], T, 50).warnings) == 2


def test_a_poi_connects_segments_that_are_far_apart():
    items = [item(0, pt(0), pt(100, poi=POI_A)), item(1, pt(800, poi=POI_A), pt(900))]
    assert validate(items, T, 50).is_valid
    items = [item(0, pt(0), pt(100, poi=POI_A)), item(1, pt(800, poi=POI_B), pt(900))]
    assert kinds(validate(items, T, 50).warnings) == ["gap"]


def test_a_missing_location_is_an_error_not_a_warning():
    items = [item(0, None, pt(100)), item(1, pt(100), pt(200))]
    result = validate(items, T, 50)
    assert kinds(result.errors) == ["missing_location"] and result.warnings == []


def test_errors_and_warnings_are_both_reported_and_as_dicts():
    items = [item(0, pt(0), pt(100)), item(1, pt(500), None)]
    result = validate(items, T, 50)
    as_dict = result.as_dict()
    assert as_dict["is_valid"] is False and as_dict["errors"][0]["kind"] == "missing_location" and as_dict["errors"][0]["slot"] == 1
    assert {"severity", "kind", "message", "slot", "ref"} <= set(as_dict["errors"][0])


def test_the_threshold_is_a_parameter():
    items = [item(0, pt(0), pt(100)), item(1, pt(180), pt(300))]
    assert validate(items, 100, 50).is_valid
    assert not validate(items, 50, 50).is_valid


def test_check_continuity_alone_ignores_the_shape():
    items = [item(0, pt(0), pt(100)), item(0, pt(0), pt(100), ref="two defaults")]
    assert check_continuity(items, T) == []                                         # the shape is check_structure's job
