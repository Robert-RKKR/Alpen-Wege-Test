# Standard library
from types import SimpleNamespace
from uuid import UUID

# Local application
from app.explorer.services import aggregate as agg
from app.explorer.services.aggregate import DefaultSeg

HIKE, BIKE, SKI = UUID(int=11), UUID(int=12), UUID(int=13)
L_EASY, L_MID, L_HARD = UUID(int=21), UUID(int=22), UUID(int=23)
G_T2, G_T5, G_K3, G_ALT = UUID(int=31), UUID(int=32), UUID(int=33), UUID(int=34)


def seg(slot, sport=HIKE, dist=1000, gain=100, loss=20, high=2000, low=1500, reverse=False, **kw):
    return DefaultSeg(slot=slot, segment_id=UUID(int=100 + slot), is_reversed=reverse, sport_type_id=sport, distance_m=dist,
                      elevation_gain_m=gain, elevation_loss_m=loss, highest_elevation_m=high, lowest_elevation_m=low, **kw)


# ------------------------------------------------------------------ totals
def test_totals_sum_distance_and_elevation_and_take_the_extremes():
    t = agg.route_totals([seg(0, dist=1000, gain=100, loss=20, high=2000, low=1500), seg(1, dist=2500, gain=300, loss=50, high=2400, low=1400)])
    assert t == {"agg_distance_m": 3500, "agg_elevation_gain_m": 400, "agg_elevation_loss_m": 70, "agg_highest_point_m": 2400,
                 "agg_lowest_point_m": 1400, "agg_duration_s": None}


def test_a_reversed_segment_exchanges_ascent_and_descent_but_not_the_extremes():
    t = agg.route_totals([seg(0, gain=100, loss=20), seg(1, gain=300, loss=50, reverse=True, high=3000, low=1000)])
    assert t["agg_elevation_gain_m"] == 100 + 50 and t["agg_elevation_loss_m"] == 20 + 300
    assert t["agg_highest_point_m"] == 3000 and t["agg_lowest_point_m"] == 1000


def test_a_route_without_segments_has_no_totals():
    assert agg.route_totals([]) == {name: None for name in agg.AGG_FIELDS}


def test_missing_values_are_skipped_and_all_missing_stays_none():
    t = agg.route_totals([seg(0, gain=None, loss=None, high=None, low=None), seg(1, gain=40, loss=None, high=1800, low=None)])
    assert t["agg_elevation_gain_m"] == 40 and t["agg_elevation_loss_m"] is None and t["agg_highest_point_m"] == 1800 and t["agg_lowest_point_m"] is None
    only_none = agg.route_totals([seg(0, dist=None, gain=None, loss=None, high=None, low=None)])
    assert only_none["agg_distance_m"] is None and only_none["agg_elevation_gain_m"] is None


# ------------------------------------------------------------------ sports
def test_the_sport_with_the_most_distance_comes_first():
    result = agg.sport_breakdown([seg(0, HIKE, dist=3000), seg(1, BIKE, dist=15000), seg(2, HIKE, dist=4000)])
    assert result == [{"sport_type_id": BIKE, "distance_m": 15000, "segment_count": 1}, {"sport_type_id": HIKE, "distance_m": 7000, "segment_count": 2}]


def test_equal_distance_keeps_the_earlier_slot_first():
    result = agg.sport_breakdown([seg(0, BIKE, dist=500), seg(1, HIKE, dist=500)])
    assert [r["sport_type_id"] for r in result] == [BIKE, HIKE]
    result = agg.sport_breakdown([seg(1, HIKE, dist=500), seg(0, BIKE, dist=500)])           # given in another order
    assert [r["sport_type_id"] for r in result] == [BIKE, HIKE]


def test_no_sport_no_breakdown():
    assert agg.sport_breakdown([]) == [] and agg.sport_breakdown([seg(0, sport=None)]) == []


# ------------------------------------------------------------------ classification
def test_the_difficulty_level_is_the_highest_rank():
    segs = [seg(0, difficulty_level_id=L_EASY, difficulty_level_rank=2), seg(1, difficulty_level_id=L_HARD, difficulty_level_rank=5),
            seg(2, difficulty_level_id=L_MID, difficulty_level_rank=3)]
    assert agg.derive_classification(segs)["difficulty_level_id"] == L_HARD


def test_equal_ranks_the_earlier_slot_wins_and_segments_without_a_value_are_ignored():
    segs = [seg(2, difficulty_level_id=L_HARD, difficulty_level_rank=4), seg(0, difficulty_level_id=L_MID, difficulty_level_rank=4), seg(1)]
    assert agg.derive_classification(segs)["difficulty_level_id"] == L_MID
    assert agg.derive_classification([seg(0), seg(1)])["difficulty_level_id"] is None


def test_the_grade_comes_from_the_main_sport_and_only_a_grade_of_that_sport():
    segs = [
        seg(0, HIKE, dist=5000, difficulty_sport_id=G_T2, difficulty_sport_rank=2, difficulty_sport_sport_type_id=HIKE),
        seg(1, BIKE, dist=900, difficulty_sport_id=G_K3, difficulty_sport_rank=9, difficulty_sport_sport_type_id=BIKE),   # harder, but another sport
        seg(2, HIKE, dist=1000, difficulty_sport_id=G_T5, difficulty_sport_rank=5, difficulty_sport_sport_type_id=HIKE),
    ]
    result = agg.derive_classification(segs)
    assert result["sport_type_id"] == HIKE and result["difficulty_sport_id"] == G_T5


def test_a_grade_of_another_sport_type_on_a_segment_of_the_main_sport_is_not_compared():
    segs = [seg(0, HIKE, difficulty_sport_id=G_ALT, difficulty_sport_rank=9, difficulty_sport_sport_type_id=SKI),
            seg(1, HIKE, difficulty_sport_id=G_T2, difficulty_sport_rank=2, difficulty_sport_sport_type_id=HIKE)]
    assert agg.derive_classification(segs)["difficulty_sport_id"] == G_T2
    only_wrong = [seg(0, HIKE, difficulty_sport_id=G_ALT, difficulty_sport_rank=9, difficulty_sport_sport_type_id=SKI)]
    assert agg.derive_classification(only_wrong)["difficulty_sport_id"] is None
    open_grade = [seg(0, HIKE, difficulty_sport_id=G_ALT, difficulty_sport_rank=3, difficulty_sport_sport_type_id=None)]   # a grade for all sports
    assert agg.derive_classification(open_grade)["difficulty_sport_id"] == G_ALT


def test_a_segment_of_another_sport_does_not_give_the_grade_even_if_its_grade_fits_every_sport():
    segs = [seg(0, HIKE, dist=5000, difficulty_sport_id=G_T2, difficulty_sport_rank=2, difficulty_sport_sport_type_id=HIKE),
            seg(1, BIKE, dist=900, difficulty_sport_id=G_ALT, difficulty_sport_rank=9, difficulty_sport_sport_type_id=None)]
    assert agg.derive_classification(segs)["difficulty_sport_id"] == G_T2


def test_a_grade_without_a_rank_is_ignored():
    assert agg.derive_classification([seg(0, difficulty_level_id=L_HARD, difficulty_level_rank=None)])["difficulty_level_id"] is None


def test_nothing_to_derive_gives_none_everywhere():
    assert agg.derive_classification([]) == {"sport_type_id": None, "difficulty_level_id": None, "difficulty_sport_id": None}


# ------------------------------------------------------------------ never overwrite a value
def route(**kw):
    return SimpleNamespace(sport_type_id=kw.get("sport"), difficulty_level_id=kw.get("level"), difficulty_sport_id=kw.get("grade"))


def test_only_empty_fields_are_filled():
    r = route(sport=BIKE)
    changed = agg.fill_empty_classification(r, {"sport_type_id": HIKE, "difficulty_level_id": L_HARD, "difficulty_sport_id": None})
    assert changed == ["difficulty_level_id"] and r.sport_type_id == BIKE and r.difficulty_level_id == L_HARD and r.difficulty_sport_id is None


def test_a_value_set_by_hand_is_never_changed():
    r = route(sport=BIKE, level=L_EASY, grade=G_T2)
    assert agg.fill_empty_classification(r, {"sport_type_id": HIKE, "difficulty_level_id": L_HARD, "difficulty_sport_id": G_T5}) == []
    assert (r.sport_type_id, r.difficulty_level_id, r.difficulty_sport_id) == (BIKE, L_EASY, G_T2)


def test_the_difference_between_stored_and_derived_is_reported():
    derived = {"sport_type_id": HIKE, "difficulty_level_id": L_HARD, "difficulty_sport_id": None}
    assert agg.classification_differs(route(sport=HIKE, level=L_HARD), derived) is False
    assert agg.classification_differs(route(sport=BIKE, level=L_HARD), derived) is True
    assert agg.classification_differs(route(sport=HIKE), derived) is True              # the level was cleared
