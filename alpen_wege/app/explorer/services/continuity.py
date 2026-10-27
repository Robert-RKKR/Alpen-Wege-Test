# Standard library
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

# Local application
from app.explorer.services.gpx.cleaning import haversine


@dataclass(frozen=True)
class EndPoint:
    # One end of a segment: where it is and, when known, the POI it starts or ends at
    lon: float
    lat: float
    poi_id: UUID | None = None


@dataclass
class SlotItem:
    # One segment row of a route as the checks see it (a saved segment, or a drawing that is not saved yet)
    ref: str                      # text for messages: the segment id, or "item 3" for an unsaved drawing
    slot: int                     # slot_position
    is_default: bool
    is_reversed: bool
    start: EndPoint | None
    end: EndPoint | None
    alt_group: int | None = None
    segment_id: UUID | None = None

    def effective_start(self) -> EndPoint | None:
        return self.end if self.is_reversed else self.start

    def effective_end(self) -> EndPoint | None:
        return self.start if self.is_reversed else self.end


@dataclass
class Issue:
    severity: str                 # "error" or "warning"
    kind: str
    message: str
    slot: int | None = None
    distance_m: float | None = None
    ref: str | None = None

    def as_dict(self) -> dict:
        out = {"severity": self.severity, "kind": self.kind, "message": self.message, "slot": self.slot, "ref": self.ref}
        if self.distance_m is not None:
            out["distance_m"] = round(self.distance_m, 1)
        return out


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        # strict validation accepts only a result without any error or warning
        return not self.errors and not self.warnings

    def as_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "errors": [i.as_dict() for i in self.errors],
            "warnings": [i.as_dict() for i in self.warnings],
        }


def distance_m(a: EndPoint, b: EndPoint) -> float:
    return haversine(a.lat, a.lon, b.lat, b.lon)


def connected(a: EndPoint, b: EndPoint, threshold_m: float) -> tuple[bool, float]:
    # Connected = the same POI, or at most threshold_m apart. A different POI does not fail by itself: the distance decides.
    d = distance_m(a, b)
    if a.poi_id is not None and a.poi_id == b.poi_id:
        return True, d
    return d <= threshold_m, d


def check_structure(items: list[SlotItem], max_segments: int) -> list[Issue]:
    # Slots 0..n-1 without gaps, alt_group equal to the slot (v1: no multi-slot alternatives), exactly one default per slot,
    # no segment twice in one slot, not more than max_segments rows.
    issues: list[Issue] = []
    if len(items) > max_segments:
        issues.append(Issue("error", "too_many_segments", f"A route can have at most {max_segments} segment rows; {len(items)} were sent."))
    by_slot: dict[int, list[SlotItem]] = defaultdict(list)
    for it in items:
        by_slot[it.slot].append(it)
    slots = sorted(by_slot)
    if slots and slots != list(range(len(slots))):
        issues.append(Issue("error", "slot_gap", f"slot_position must be 0 to {len(slots) - 1} without gaps; got {slots}."))
    for slot in slots:
        group = by_slot[slot]
        for it in group:
            if it.alt_group is not None and it.alt_group != slot:
                issues.append(Issue("error", "alt_group_mismatch", "alt_group must equal slot_position (alternatives share one slot).", slot, ref=it.ref))
        defaults = [it for it in group if it.is_default]
        if len(defaults) == 0:
            issues.append(Issue("error", "no_default", f"Slot {slot} has no default segment.", slot))
        elif len(defaults) > 1:
            issues.append(Issue("error", "multiple_defaults", f"Slot {slot} has {len(defaults)} default segments; exactly one is allowed.", slot))
        seen: set = set()
        for it in group:
            key = it.segment_id if it.segment_id is not None else it.ref
            if key in seen:
                issues.append(Issue("error", "duplicate_in_slot", f"The same segment is twice in slot {slot}.", slot, ref=it.ref))
            seen.add(key)
    return issues


def check_continuity(items: list[SlotItem], threshold_m: float) -> list[Issue]:
    # 1. every row needs a start and an end location
    # 2. every alternative starts and ends where the default of its slot starts and ends
    # 3. the default of each slot ends where the default of the next slot starts
    # (2 and 3 together prove that every path through the alternatives is connected)
    issues: list[Issue] = []
    for it in items:
        if it.start is None or it.end is None:
            issues.append(Issue("error", "missing_location", f"{it.ref} has no start or end location.", it.slot, ref=it.ref))
    by_slot: dict[int, list[SlotItem]] = defaultdict(list)
    for it in items:
        by_slot[it.slot].append(it)
    defaults: dict[int, SlotItem] = {}
    for slot in sorted(by_slot):
        group = by_slot[slot]
        default = next((it for it in group if it.is_default), None)
        if default is None:
            continue
        defaults[slot] = default
        for alt in group:
            if alt is default:
                continue
            for label, mine, theirs in (
                ("alternative_start_mismatch", alt.effective_start(), default.effective_start()),
                ("alternative_end_mismatch", alt.effective_end(), default.effective_end()),
            ):
                if mine is None or theirs is None:
                    continue
                ok, d = connected(mine, theirs, threshold_m)
                if not ok:
                    where = "starts" if label.endswith("start_mismatch") else "ends"
                    issues.append(Issue("warning", label, f"{alt.ref} {where} {d:.0f} m from where the default of slot {slot} {where}.", slot, d, alt.ref))
    ordered = sorted(defaults)
    for prev, nxt in zip(ordered, ordered[1:]):
        a, b = defaults[prev].effective_end(), defaults[nxt].effective_start()
        if a is None or b is None:
            continue
        ok, d = connected(a, b, threshold_m)
        if not ok:
            issues.append(Issue("warning", "gap", f"Slot {prev} ends {d:.0f} m from where slot {nxt} starts.", prev, d, defaults[nxt].ref))
    return issues


def validate(items: list[SlotItem], threshold_m: float, max_segments: int) -> ValidationResult:
    result = ValidationResult()
    result.errors.extend(check_structure(items, max_segments))
    for issue in check_continuity(items, threshold_m):
        (result.errors if issue.severity == "error" else result.warnings).append(issue)
    return result
