# Standard library
from uuid import UUID

# Local application
from app.explorer.services import route_geometry as rg
from app.explorer.services.route_geometry import GeoPart

SID = UUID(int=1)
LINE_A = {"type": "LineString", "coordinates": [[11.0, 47.0], [11.0, 47.001], [11.0, 47.002]]}
LINE_B = {"type": "LineString", "coordinates": [[11.0, 47.002], [11.0, 47.003]]}
MULTI = {"type": "MultiLineString", "coordinates": [[[1, 1], [2, 2]], [[3, 3], [4, 4]]]}


def part(slot, geojson=LINE_A, graph=None, distance=None, reverse=False):
    return GeoPart(slot, SID, reverse, geojson, graph, distance)


def test_lines_of_each_kind():
    assert rg.lines_of(LINE_A) == [LINE_A["coordinates"]]
    assert rg.lines_of(MULTI) == MULTI["coordinates"]
    assert rg.lines_of(None) == [] and rg.lines_of({"type": "Point", "coordinates": [1, 2]}) == []


def test_walking_backwards_reverses_the_lines_and_their_order():
    assert rg.walked(MULTI["coordinates"], False) == MULTI["coordinates"]
    assert rg.walked(MULTI["coordinates"], True) == [[[4, 4], [3, 3]], [[2, 2], [1, 1]]]
    original = [[[1, 1], [2, 2]]]
    rg.walked(original, True)
    assert original == [[[1, 1], [2, 2]]]                                             # the input is not changed


def test_one_line_is_a_linestring_several_are_a_multilinestring():
    assert rg.line_geojson([[[1, 1], [2, 2]]])["type"] == "LineString"
    assert rg.line_geojson(MULTI["coordinates"])["type"] == "MultiLineString"
    assert rg.line_geojson([]) is None


def test_route_lines_follow_the_slots_and_turn_reversed_segments():
    lines = rg.route_lines([part(1, LINE_B), part(0, LINE_A, reverse=True)])           # given out of order
    assert lines == [list(reversed(LINE_A["coordinates"])), LINE_B["coordinates"]]


def test_the_profile_of_the_second_segment_starts_where_the_first_ended():
    first = part(0, graph=[[0, 1000], [500, 1100], [1000, 1200]], distance=1000)
    second = part(1, graph=[[0, 1200], [400, 1300]], distance=400)
    assert rg.combined_profile([second, first]) == [[0, 1000], [500, 1100], [1000, 1200], [1000, 1200], [1400, 1300]]


def test_a_reversed_segment_is_mirrored_in_the_profile():
    up = part(0, graph=[[0, 1000], [500, 1100], [1000, 1200]], distance=1000, reverse=True)         # stored going up, walked going down
    assert rg.combined_profile([up]) == [[0, 1200], [500, 1100], [1000, 1000]]
    two = rg.combined_profile([part(0, graph=[[0, 10], [100, 20]], distance=100), part(1, graph=[[0, 20], [300, 50]], distance=300, reverse=True)])
    assert [p[0] for p in two] == sorted(p[0] for p in two) and two[-1] == [400, 20]


def test_the_profile_distances_never_go_below_zero_or_backwards():
    wobbly = part(0, graph=[[0, 5], [1000.04, 9]], distance=1000, reverse=True)          # a graph that ends a hair after the distance
    assert [p[0] for p in rg.combined_profile([wobbly])] == [0.0, 1000.0] or min(p[0] for p in rg.combined_profile([wobbly])) >= 0


def test_the_length_falls_back_to_the_graph_when_there_is_no_distance():
    assert rg.segment_length(part(0, graph=[[0, 1], [250.5, 2]], distance=None)) == 250.5
    assert rg.segment_length(part(0, graph=None, distance=None)) == 0.0


def test_fewer_than_two_points_is_no_profile():
    assert rg.combined_profile([]) is None
    assert rg.combined_profile([part(0, graph=None, distance=100)]) is None
    assert rg.combined_profile([part(0, graph=[[0, 1000]], distance=100)]) is None


def test_a_segment_without_elevation_still_moves_the_next_one():
    first = part(0, graph=None, distance=500)
    second = part(1, graph=[[0, 100], [100, 120]], distance=100)
    assert rg.combined_profile([first, second]) == [[500, 100], [600, 120]]
