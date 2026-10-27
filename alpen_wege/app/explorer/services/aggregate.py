# Standard library
from dataclasses import dataclass
from uuid import UUID


@dataclass
class DefaultSeg:
    # What the totals and the classification need to know about one default segment of a route, in slot order
    slot: int
    segment_id: UUID
    is_reversed: bool = False
    sport_type_id: UUID | None = None
    difficulty_level_id: UUID | None = None
    difficulty_level_rank: int | None = None
    difficulty_sport_id: UUID | None = None
    difficulty_sport_rank: int | None = None
    difficulty_sport_sport_type_id: UUID | None = None   # the sport type the grade belongs to
    distance_m: int | None = None
    elevation_gain_m: int | None = None
    elevation_loss_m: int | None = None
    highest_elevation_m: int | None = None
    lowest_elevation_m: int | None = None

    def traversed_gain_loss(self) -> tuple[int | None, int | None]:
        # walked backwards, what was ascent becomes descent
        if self.is_reversed:
            return self.elevation_loss_m, self.elevation_gain_m
        return self.elevation_gain_m, self.elevation_loss_m


AGG_FIELDS = (
    "agg_distance_m", "agg_elevation_gain_m", "agg_elevation_loss_m", "agg_highest_point_m", "agg_lowest_point_m",
    "agg_duration_s",
)


def _sum(values: list[int | None]) -> int | None:
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def route_totals(segs: list[DefaultSeg]) -> dict[str, int | None]:
    # Totals of the default segments only. A route without segments has no totals. agg_duration_s stays empty: segments
    # carry no time; the Prediction fills it later.
    if not segs:
        return {name: None for name in AGG_FIELDS}
    gains, losses = zip(*(s.traversed_gain_loss() for s in segs))
    highs = [s.highest_elevation_m for s in segs if s.highest_elevation_m is not None]
    lows = [s.lowest_elevation_m for s in segs if s.lowest_elevation_m is not None]
    return {
        "agg_distance_m": _sum([s.distance_m for s in segs]),
        "agg_elevation_gain_m": _sum(list(gains)),
        "agg_elevation_loss_m": _sum(list(losses)),
        "agg_highest_point_m": max(highs) if highs else None,
        "agg_lowest_point_m": min(lows) if lows else None,
        "agg_duration_s": None,
    }


def sport_breakdown(segs: list[DefaultSeg]) -> list[dict]:
    # The sports of the default segments, the one with the most distance first (equal distance: the earlier slot first)
    order: dict[UUID, dict] = {}
    for s in sorted(segs, key=lambda s: s.slot):
        if s.sport_type_id is None:
            continue
        entry = order.setdefault(s.sport_type_id, {"sport_type_id": s.sport_type_id, "distance_m": 0, "segment_count": 0, "first_slot": s.slot})
        entry["distance_m"] += s.distance_m or 0
        entry["segment_count"] += 1
    ranked = sorted(order.values(), key=lambda e: (-e["distance_m"], e["first_slot"]))
    return [{k: v for k, v in e.items() if k != "first_slot"} for e in ranked]


def derive_classification(segs: list[DefaultSeg]) -> dict[str, UUID | None]:
    # sport_type_id: the sport with the most distance.
    # difficulty_level_id: the highest rank among the levels of the segments.
    # difficulty_sport_id: the highest rank among the grades of the segments of the primary sport, and only grades of
    #   that sport type (grades of different sport types cannot be compared).
    # Segments without a value are ignored; nothing to derive gives None. Equal ranks: the earlier slot wins.
    ordered = sorted(segs, key=lambda s: s.slot)
    breakdown = sport_breakdown(ordered)
    sport = breakdown[0]["sport_type_id"] if breakdown else None
    level = None
    best = None
    for s in ordered:
        if s.difficulty_level_id is not None and s.difficulty_level_rank is not None and (best is None or s.difficulty_level_rank > best):
            level, best = s.difficulty_level_id, s.difficulty_level_rank
    grade = None
    best = None
    for s in ordered:
        if s.sport_type_id != sport or s.difficulty_sport_id is None or s.difficulty_sport_rank is None:
            continue
        if s.difficulty_sport_sport_type_id not in (None, sport):
            continue
        if best is None or s.difficulty_sport_rank > best:
            grade, best = s.difficulty_sport_id, s.difficulty_sport_rank
    return {"sport_type_id": sport, "difficulty_level_id": level, "difficulty_sport_id": grade}


CLASSIFICATION_FIELDS = ("sport_type_id", "difficulty_level_id", "difficulty_sport_id")


def fill_empty_classification(route, derived: dict) -> list[str]:
    # Sets the fields of the route that are empty from the derived values; never changes one that has a value.
    # Returns the names that were set.
    changed = []
    for name in CLASSIFICATION_FIELDS:
        if getattr(route, name) is None and derived.get(name) is not None:
            setattr(route, name, derived[name])
            changed.append(name)
    return changed


def classification_differs(route, derived: dict) -> bool:
    return any(getattr(route, name) != derived.get(name) for name in CLASSIFICATION_FIELDS)
