"""Suggest traverse routes from the observation graph.

A traverse leg exists between two points when a distance was measured between them
and the point we continue from is an occupied station that also observed the previous
point (so the angle can be formed). Starting from every known station that observes a
known orientation point, we walk through unknown occupied stations until we reach a
known point. Preference order: link/closed with closing azimuth > on position only >
open. Every unknown occupied station is covered at most once.
"""

from __future__ import annotations

from .issues import IssueSink
from .models import ProjectInput, TraverseSpec
from .reduce import ObservationIndex, reduce_setups


def suggest_traverses(inp: ProjectInput, max_len: int = 40) -> list[TraverseSpec]:
    sink = IssueSink()
    reduced = reduce_setups(inp.setups, inp.settings.reduction, inp.settings.tolerances, sink)
    index = ObservationIndex(reduced)
    known = {c.name for c in inp.control_points}
    stations = index.stations()

    def observes(station: str, target: str) -> bool:
        return any(target in s.targets for s in index.by_station.get(station, []))

    def has_leg(a: str, b: str) -> bool:
        return index.leg(a, b) is not None

    def angle_ok(prev: str, st: str, nxt: str) -> bool:
        return index.angle(st, prev, nxt) is not None

    def neighbours(st: str) -> list[str]:
        out: set[str] = set()
        for s in index.by_station.get(st, []):
            out.update(s.targets)
        for other, sets in index.by_station.items():
            if any(st in s.targets for s in sets):
                out.add(other)
        out.discard(st)
        return sorted(out)

    candidates: list[tuple[int, list[str]]] = []

    def walk(path: list[str]) -> None:
        if len(path) > max_len:
            return
        prev, cur = path[-2], path[-1]
        for nxt in neighbours(cur):
            if nxt in path[1:] and not (nxt == path[1] and len(path) > 3):
                continue
            if not has_leg(cur, nxt) or not angle_ok(prev, cur, nxt):
                continue
            new = [*path, nxt]
            if nxt in known:
                # try to close on azimuth from the end station
                closed_orient = False
                for orient in neighbours(nxt):
                    if orient in known and orient != cur and angle_ok(cur, nxt, orient):
                        candidates.append((3, [*new, orient]))
                        closed_orient = True
                        break
                if not closed_orient:
                    candidates.append((2, new))
            elif nxt in stations:
                walk(new)
            elif cur not in known:
                # hanging end of an open traverse (sighted but never occupied)
                candidates.append((1, new))
        if cur not in known and cur in stations and len(path) >= 3:
            candidates.append((1, path))

    for st in sorted(stations & known):
        for orient in neighbours(st):
            if orient in known and observes(st, orient):
                walk([orient, st])

    # rank: quality, then number of new points (longer first), then name order
    def new_points(route: list[str]) -> list[str]:
        return [p for p in route if p not in known]

    candidates.sort(key=lambda c: (-c[0], -len(new_points(c[1])), c[1]))
    covered: set[str] = set()
    out: list[TraverseSpec] = []
    for quality, route in candidates:
        np = new_points(route)
        if not np or covered.intersection(np):
            continue
        covered.update(np)
        kind = "auto" if quality > 1 else "open"
        out.append(TraverseSpec(route=route, kind=kind, name="-".join(route)))
    return out
