# Standard library
import csv
from collections import defaultdict
from pathlib import Path

# Third-party
import pytest
from pydantic import ValidationError
from sqlalchemy import Index, SmallInteger, UniqueConstraint

# Local application
from app.core.models.models_ref import (
    CoreRefDifficultyLevel,
    CoreRefDifficultySport,
    CoreRefRarity,
    CoreRefVisibility,
)
from app.core.schemas.ref import (
    DifficultySportCreate,
    DifficultySportUpdate,
    RANK_MAX,
    RefBaseUpdate,
    RefRankedCreate,
    RefRankedUpdate,
    RefWithFactorUpdate,
)
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_m2m.route_journey import ExplorerM2mRouteJourney
from app.explorer.models.models_m2m.segment_route import ExplorerM2mSegmentRoute
from app.core.models import models_ref

ROOT = Path(__file__).resolve().parents[1]
RANKED = {
    "core_ref_difficulty_level": CoreRefDifficultyLevel,
    "core_ref_difficulty_sport": CoreRefDifficultySport,
    "core_ref_rarity": CoreRefRarity,
    "core_ref_visibility": CoreRefVisibility,
}
NEW = {"name": "x", "color": "#000000", "icon_id": "00000000-0000-0000-0000-000000000001", "point_factor": 1.0}


# ------------------------------------------------------------------ rank (decision D2, C1)

def test_exactly_the_four_scale_tables_have_a_rank():
    with_rank = {
        cls.__tablename__ for name in models_ref.__all__
        if (cls := getattr(models_ref, name)) and hasattr(cls, "__tablename__") and "rank" in cls.__table__.columns
    }
    assert with_rank == set(RANKED)


@pytest.mark.parametrize("table,model", RANKED.items())
def test_rank_is_a_required_smallint(table, model):
    column = model.__table__.columns["rank"]
    assert isinstance(column.type, SmallInteger) and column.nullable is False and column.server_default is None


def test_a_ranked_table_cannot_be_created_without_a_rank():
    with pytest.raises(ValidationError):
        RefRankedCreate(**NEW)
    with pytest.raises(ValidationError):
        DifficultySportCreate(**NEW)
    assert RefRankedCreate(**NEW, rank=0).rank == 0
    assert DifficultySportCreate(**NEW, rank=3, sport_type_id=None).rank == 3


@pytest.mark.parametrize("bad", [-1, RANK_MAX + 1, 40000, "x", 1.5])
def test_rank_must_be_a_small_integer(bad):
    with pytest.raises(ValidationError):
        RefRankedCreate(**NEW, rank=bad)
    with pytest.raises(ValidationError):
        RefRankedUpdate(rank=bad)


def test_rank_is_optional_on_update_and_not_sent_means_not_changed():
    assert RefRankedUpdate().model_dump(exclude_unset=True) == {}
    assert RefRankedUpdate(rank=2).model_dump(exclude_unset=True) == {"rank": 2}


@pytest.mark.parametrize("schema,field", [
    (RefRankedUpdate, "rank"), (RefRankedUpdate, "point_factor"), (RefRankedUpdate, "color"), (RefRankedUpdate, "icon_id"),
    (DifficultySportUpdate, "rank"), (RefWithFactorUpdate, "point_factor"), (RefBaseUpdate, "color"), (RefBaseUpdate, "icon_id"),
])
def test_a_required_column_cannot_be_set_to_null_by_an_update(schema, field):
    # explicit null used to reach the database and end in a 500; now it is a 422, and a name may still be emptied
    with pytest.raises(ValidationError):
        schema(**{field: None})
    assert schema(name=None).model_dump(exclude_unset=True) == {"name": None}


# ------------------------------------------------------------------ the seed files carry the rank

def _csv(name):
    with open(ROOT / "push_data" / f"core_ref_{name}.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("name", ["difficulty_level", "difficulty_sport", "rarity", "visibility"])
def test_the_seed_csv_has_a_rank_for_every_row(name):
    rows = _csv(name)
    assert rows and all(r["rank"].strip().isdigit() and 1 <= int(r["rank"]) <= RANK_MAX for r in rows)


def test_rank_follows_point_factor_inside_a_scale():
    # the first ranks were derived from point_factor (equal factor = equal rank, higher factor = higher rank)
    for name in ("difficulty_level", "rarity"):
        rows = sorted(_csv(name), key=lambda r: float(r["point_factor"]))
        ranks = [int(r["rank"]) for r in rows]
        assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks), name
    groups = defaultdict(list)
    for r in _csv("difficulty_sport"):
        groups[r["sport_type_id"]].append((float(r["point_factor"]), int(r["rank"])))
    for sport, items in groups.items():
        items.sort()
        assert [rank for _, rank in items] == sorted(rank for _, rank in items), sport
        assert min(rank for _, rank in items) == 1, sport
        for (f1, r1), (f2, r2) in zip(items, items[1:]):
            assert (f1 == f2) == (r1 == r2), (sport, f1, f2)


def test_the_visibility_scale_goes_from_best_to_worst():
    rows = {r["name"]: int(r["rank"]) for r in _csv("visibility")}
    assert rows["Excellent"] == 1 and rows["Whiteout"] == max(rows.values()) == 8
    assert len(set(rows.values())) == len(rows)


def test_the_other_reference_files_got_no_rank_column():
    for name in ("snow_condition", "trail_condition", "weather_condition", "schedule_status", "sport_type", "gear_type"):
        assert "rank" not in _csv(name)[0], name


# ------------------------------------------------------------------ route, segment_route, route_journey (D1, D4, C5)

@pytest.mark.parametrize("column", ["sport_type_id", "difficulty_level_id", "difficulty_sport_id"])
def test_a_draft_route_may_have_no_classification(column):
    assert ExplorerAggRoute.__table__.columns[column].nullable is True


def _ondelete(model, column):
    (fk,) = model.__table__.columns[column].foreign_keys
    return fk.ondelete


def test_a_used_segment_or_route_cannot_be_deleted_by_the_database():
    assert _ondelete(ExplorerM2mSegmentRoute, "segment_id") == "RESTRICT"
    assert _ondelete(ExplorerM2mRouteJourney, "route_id") == "RESTRICT"
    # the parents may still take their own link rows with them
    assert _ondelete(ExplorerM2mSegmentRoute, "route_id") == "CASCADE"
    assert _ondelete(ExplorerM2mRouteJourney, "journey_id") == "CASCADE"


def _named(model, kind):
    return {c.name: c for c in model.__table__.constraints if isinstance(c, kind)} | {
        i.name: i for i in model.__table__.indexes if kind is Index
    }


def test_segment_route_rules():
    uniques = {tuple(c.name for c in u.columns) for u in model_uniques(ExplorerM2mSegmentRoute)}
    assert ("route_id", "slot_position", "segment_id") in uniques
    one_default = _named(ExplorerM2mSegmentRoute, Index)["uq_segment_route_one_default"]
    assert one_default.unique and [c.name for c in one_default.columns] == ["route_id", "alt_group"]
    assert "is_default" in str(one_default.dialect_options["postgresql"]["where"])
    assert "ix_segment_route_segment_id" in _named(ExplorerM2mSegmentRoute, Index)


def test_route_journey_rules():
    uniques = {tuple(c.name for c in u.columns) for u in model_uniques(ExplorerM2mRouteJourney)}
    assert ("journey_id", "slot_position") in uniques
    assert "ix_route_journey_route_id" in _named(ExplorerM2mRouteJourney, Index)


def model_uniques(model):
    return [c for c in model.__table__.constraints if isinstance(c, UniqueConstraint)]
