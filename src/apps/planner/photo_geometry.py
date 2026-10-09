"""Tidying what Claude traced in the photo before it reaches the editor (US-129).

Claude reads a sketch the way a person would: the corner is there, but its two
walls stop a few pixels apart, a partition ends just short of the wall it meets,
and a room behind a door is open exactly where the door is. The editor needs the
drawing as built — corners that meet and rooms that close — so this joins what
is meant to touch and closes each room over its doorways, without filling the
doorway itself: the gap stays in the walls.

Everything works in pixels of the polished photo. Distances are thought of in
metres and turned into pixels with the photo's scale: the provisional one the
editor gives it (1 px = 1 cm) unless a better one is known.
"""

import math

Point = tuple[float, float]
Segment = tuple[Point, Point]

# La escala provisional del editor para una foto (US-41): 1 px = 1 cm.
PROVISIONAL_METRES_PER_PIXEL = 0.01
# Dos extremos a menos de esto son la misma esquina: un muro de grueso.
JOIN_METRES = 0.15
# El hueco más ancho que todavía es una puerta o un paso entre dos cuartos.
DOORWAY_METRES = 1.20
# Lo más lejos que puede quedar del eje del muro el borde de una puerta o una
# ventana dibujada en él: medio muro grueso, con el pulso del dibujo.
OPENING_REACH_METRES = 0.30
# Lo cerrado más chico que se da por cuarto, y su ancho mínimo: un ducto o el
# hueco entre las dos líneas de un muro grueso no lo son.
MIN_ROOM_AREA_M2 = 0.5
MIN_ROOM_WIDTH_M = 0.4

# Un muro a menos de esto de la horizontal, la vertical o la diagonal se dibujó
# así: lo que se aparta es la hoja pandeada o el pulso, no la obra.
SQUARE_DEGREES = 8
SQUARE_ANGLES = (0, 45, 90, 135, 180)

# Dos muros a menos de esto de paralelos siguen la misma línea.
PARALLEL_DEGREES = 5
# Por debajo de esto (seno² del ángulo entre muros) no hay esquina que buscar.
CORNER_SIN2 = math.sin(math.radians(13)) ** 2
# Lo que mide el error de coma flotante, en píxeles.
EPS = 1e-4


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _add(a: Point, v: Point, s: float = 1.0) -> Point:
    return (a[0] + v[0] * s, a[1] + v[1] * s)


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _unit(v: Point) -> Point:
    length = math.hypot(*v)
    return (v[0] / length, v[1] / length)


def _key(p: Point) -> Point:
    return (round(p[0], 3), round(p[1], 3))


def _closest(p: Point, a: Point, b: Point) -> tuple[float, Point]:
    """Where p falls along a→b (0 at a, 1 at b) and the nearest point there."""
    ab = _sub(b, a)
    t = _dot(_sub(p, a), ab) / _dot(ab, ab)
    t = min(max(t, 0.0), 1.0)
    return t, _add(a, ab, t)


def _lines_meet(p: Point, d: Point, q: Point, e: Point) -> Point | None:
    """Where the line through p along d meets the line through q along e."""
    denom = _cross(d, e)
    if abs(denom) < 1e-9 * math.hypot(*d) * math.hypot(*e):
        return None
    return _add(p, d, _cross(_sub(q, p), e) / denom)


def _parallel(u: Point, v: Point) -> bool:
    sin = abs(_cross(_unit(u), _unit(v)))
    return sin <= math.sin(math.radians(PARALLEL_DEGREES))


def _corner(ends: list[Point], walls: list[Segment]) -> Point:
    """The point the walls of one corner meet at, so they keep their direction.

    It is the point closest to every wall's line at once; walls that run almost
    the same way have no such point worth trusting, and then the ends meet half
    way between them.
    """
    mean = (sum(p[0] for p in ends) / len(ends), sum(p[1] for p in ends) / len(ends))
    sxx = sxy = syy = bx = by = 0.0
    for a, b in walls:
        nx, ny = _unit((a[1] - b[1], b[0] - a[0]))
        c = nx * a[0] + ny * a[1]
        sxx += nx * nx
        sxy += nx * ny
        syy += ny * ny
        bx += nx * c
        by += ny * c
    det = sxx * syy - sxy * sxy
    trace = sxx + syy
    if not walls or det < CORNER_SIN2 * trace * trace / 4:
        return mean
    return ((syy * bx - sxy * by) / det, (sxx * by - sxy * bx) / det)


def square_walls(walls: list[Segment]) -> list[Segment]:
    """Walls almost level, upright or at 45° come out exactly so.

    Each turns about its middle and keeps the stretch it covered along its new
    direction, so it still reaches the corners it was drawn to. A wall further
    from those angles was slanted on purpose and is left as drawn.
    """
    squared = []
    for a, b in walls:
        middle = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        drawn = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
        target = min(SQUARE_ANGLES, key=lambda angle: abs(angle - drawn))
        if abs(target - drawn) > SQUARE_DEGREES:
            squared.append((a, b))
            continue
        along = (math.cos(math.radians(target)), math.sin(math.radians(target)))
        squared.append(
            tuple(_add(middle, along, _dot(_sub(p, middle), along)) for p in (a, b))
        )
    return squared


def join_walls(walls: list[Segment], tolerance: float) -> list[Segment]:
    """Ends that are one corner meet; a wall that stops short reaches the next.

    First, ends closer than ``tolerance`` become one point, where their walls
    cross. Then an end left alone near the side of another wall — short of it
    or past it — is brought onto that wall.
    """
    ends = [p for segment in walls for p in segment]
    parent = list(range(len(ends)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(ends)):
        for j in range(i + 1, len(ends)):
            if _distance(ends[i], ends[j]) <= tolerance:
                parent[root(i)] = root(j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(ends)):
        clusters.setdefault(root(i), []).append(i)

    joined = list(ends)
    alone = set()
    for members in clusters.values():
        if len(members) == 1:
            alone.add(members[0])
            continue
        point = _corner(
            [ends[i] for i in members], list({walls[i // 2] for i in members})
        )
        if _distance(point, ends[members[0]]) > 3 * tolerance:
            point = _corner([ends[i] for i in members], [])
        for i in members:
            joined[i] = point

    segments = [(joined[2 * k], joined[2 * k + 1]) for k in range(len(walls))]
    for i in sorted(alone):
        k, end = divmod(i, 2)
        own = segments[k]
        p = own[end]
        best = None
        for other, (a, b) in enumerate(segments):
            if other == k or _distance(a, b) == 0:
                continue
            _, nearest = _closest(p, a, b)
            gap = _distance(p, nearest)
            if gap <= tolerance and (best is None or gap < best[0]):
                best = (gap, a, b, nearest)
        if best is None:
            continue
        _, a, b, nearest = best
        meet = _lines_meet(own[0], _sub(own[1], own[0]), a, _sub(b, a))
        target = meet if meet and _distance(meet, p) <= 2 * tolerance else nearest
        segments[k] = (target, own[1]) if end == 0 else (own[0], target)

    return [s for s in segments if _distance(*s) > EPS]


def _holder(walls: list[Segment], p: Point, q: Point, reach: float) -> int | None:
    """The wall both edges of a door or window lie on, if any."""
    best = None
    for k, (a, b) in enumerate(walls):
        far = max(_distance(e, _closest(e, a, b)[1]) for e in (p, q))
        if far <= reach and (best is None or far < best[0]):
            best = (far, k)
    return None if best is None else best[1]


def _close_gap(
    walls: list[Segment], p: Point, q: Point, reach: float, tolerance: float
) -> list[Segment]:
    """One wall across a door the drawing left as a gap between two walls.

    Many plans cut the wall where the door goes. The door then sits on no wall;
    the two walls in line on each side of it are one wall with a door in it.
    """
    for k, (a, b) in enumerate(walls):
        for j, (c, d) in enumerate(walls):
            if j == k or not _parallel(_sub(b, a), _sub(d, c)):
                continue
            for near_k, far_k in ((a, b), (b, a)):
                for near_j, far_j in ((c, d), (d, c)):
                    in_line = (
                        abs(_cross(_unit(_sub(b, a)), _sub(near_j, a))) <= tolerance
                    )
                    if (
                        in_line
                        and _distance(near_k, p) <= reach
                        and _distance(near_j, q) <= reach
                    ):
                        merged = (far_k, far_j) if near_k == b else (far_j, far_k)
                        joined = list(walls)
                        joined[k] = merged
                        del joined[j]
                        return joined
    return walls


def place_openings(
    walls: list[Segment],
    openings: list[tuple[str, Point, Point]],
    *,
    metres_per_pixel: float,
) -> tuple[list[Segment], list[tuple[str, int, float, float]]]:
    """Each door and window on the wall it was drawn on.

    It comes back as where it starts and ends along that wall, from 0 at the
    wall's start to 1 at its end, which is all the editor needs to carve it. A
    door or window that lies on no wall is dropped rather than guessed at.
    """
    reach = OPENING_REACH_METRES / metres_per_pixel
    tolerance = JOIN_METRES / metres_per_pixel
    for _, p, q in openings:
        if _holder(walls, p, q, reach) is None:
            walls = _close_gap(walls, p, q, reach, tolerance)
            if _holder(walls, p, q, reach) is None:
                walls = _close_gap(walls, q, p, reach, tolerance)

    placed = []
    for kind, p, q in openings:
        k = _holder(walls, p, q, reach)
        if k is None:
            continue
        a, b = walls[k]
        start, end = sorted(_closest(e, a, b)[0] for e in (p, q))
        if end - start > EPS:
            placed.append((kind, k, start, end))
    return walls, placed


def _crossing(a: Point, b: Point, c: Point, d: Point) -> Point | None:
    """Where two walls cross in the middle of both, if they do."""
    r, s = _sub(b, a), _sub(d, c)
    denom = _cross(r, s)
    if abs(denom) < 1e-9:
        return None
    t = _cross(_sub(c, a), s) / denom
    u = _cross(_sub(c, a), r) / denom
    if EPS < t * math.hypot(*r) < math.hypot(*r) - EPS and (
        EPS < u * math.hypot(*s) < math.hypot(*s) - EPS
    ):
        return _add(a, r, t)
    return None


def _on_side(p: Point, a: Point, b: Point) -> bool:
    """True when p lies on the wall a→b, away from its ends."""
    t, nearest = _closest(p, a, b)
    return 0 < t < 1 and _distance(p, nearest) <= EPS * 10


def _doorways(
    walls: list[Segment], doorway: float, tolerance: float
) -> tuple[list[Segment], dict[int, list[Point]]]:
    """The lines that close each doorway, and where they land on a wall.

    A loose end of a wall looks ahead along the wall. If the same wall goes on
    within a doorway's width, the gap is a door; if another wall is that close,
    the gap is a passage. Either way the room closes across it — only for
    finding the room: the walls keep their gap.
    """
    loose = []
    for k, (a, b) in enumerate(walls):
        for end, other in ((a, b), (b, a)):
            shared = any(
                j != k and (_key(end) in (_key(c), _key(d)) or _on_side(end, c, d))
                for j, (c, d) in enumerate(walls)
            )
            if not shared:
                loose.append((k, end, _unit(_sub(end, other))))

    bridges: list[Segment] = []
    landings: dict[int, list[Point]] = {}
    seen = set()
    for k, end, ahead in loose:
        best = None
        for j, other_end, other_ahead in loose:
            if j == k:
                continue
            gap = _sub(other_end, end)
            along = _dot(gap, ahead)
            if (
                0 < along <= doorway
                and abs(_cross(ahead, gap)) <= tolerance
                and _parallel(ahead, other_ahead)
            ):
                if best is None or along < best[0]:
                    best = (along, other_end, None)
        for j, (c, d) in enumerate(walls):
            if j == k:
                continue
            hit = _lines_meet(end, ahead, c, _sub(d, c))
            if hit is None:
                continue
            along = _dot(_sub(hit, end), ahead)
            t, nearest = _closest(hit, c, d)
            if (
                EPS < along <= doorway
                and _distance(hit, nearest) <= EPS * 10
                and (best is None or along < best[0])
            ):
                best = (along, hit, j)
        if best is None:
            continue
        _, target, landed_on = best
        pair = frozenset((_key(end), _key(target)))
        if pair in seen:
            continue
        seen.add(pair)
        bridges.append((end, target))
        if landed_on is not None:
            landings.setdefault(landed_on, []).append(target)
    return bridges, landings


def _graph(walls: list[Segment], doorway: float, tolerance: float):
    """The walls as a network of corners, split wherever another wall meets them."""
    bridges, landings = _doorways(walls, doorway, tolerance)
    stops = [[a, b, *landings.get(k, [])] for k, (a, b) in enumerate(walls)]
    for k, (a, b) in enumerate(walls):
        for j, (c, d) in enumerate(walls):
            if j == k:
                continue
            stops[k].extend(p for p in (c, d) if _on_side(p, a, b))
            meet = _crossing(a, b, c, d)
            if meet is not None:
                stops[k].append(meet)

    points: dict[Point, Point] = {}
    links: dict[Point, set[Point]] = {}

    def link(p: Point, q: Point) -> None:
        kp, kq = _key(p), _key(q)
        if kp == kq:
            return
        points.setdefault(kp, p)
        points.setdefault(kq, q)
        links.setdefault(kp, set()).add(kq)
        links.setdefault(kq, set()).add(kp)

    for (a, b), along in zip(walls, stops, strict=True):
        ordered = sorted(along, key=lambda p, a=a, b=b: _dot(_sub(p, a), _sub(b, a)))
        for p, q in zip(ordered, ordered[1:], strict=False):
            link(p, q)
    for p, q in bridges:
        link(p, q)

    # Un muro que no cierra nada —un extremo suelto— no rodea ningún cuarto.
    loose = [k for k, near in links.items() if len(near) < 2]
    while loose:
        k = loose.pop()
        for other in links.pop(k, set()):
            links[other].discard(k)
            if len(links[other]) < 2:
                loose.append(other)
    return points, links


def _signed_area(polygon: list[Point]) -> float:
    pairs = zip(polygon, polygon[1:] + polygon[:1], strict=True)
    return sum(_cross(a, b) for a, b in pairs) / 2


def _perimeter(polygon: list[Point]) -> float:
    pairs = zip(polygon, polygon[1:] + polygon[:1], strict=True)
    return sum(_distance(a, b) for a, b in pairs)


def _straighten(polygon: list[Point]) -> list[Point]:
    """Without the corners that are not corners: points along a straight side."""
    kept = []
    for i, p in enumerate(polygon):
        before, after = polygon[i - 1], polygon[(i + 1) % len(polygon)]
        bend = abs(_cross(_sub(p, before), _sub(after, p)))
        if bend > EPS * max(_distance(p, before), _distance(after, p), 1.0):
            kept.append(p)
    return kept


def _faces(points: dict[Point, Point], links: dict[Point, set[Point]]):
    """Every space the network of walls closes, as a polygon.

    Walking each side of each wall and always taking the next wall around the
    corner traces every enclosed space once, turning the same way; the outside
    of the drawing comes out turning the other way and is left out.
    """
    around = {
        k: sorted(near, key=lambda n, k=k: math.atan2(n[1] - k[1], n[0] - k[0]))
        for k, near in links.items()
    }
    walked = set()
    faces = []
    for start in around:
        for first in around[start]:
            edge = (start, first)
            corners = []
            while edge not in walked:
                walked.add(edge)
                corners.append(points[edge[0]])
                came_from, here = edge
                turn = around[here]
                edge = (here, turn[(turn.index(came_from) - 1) % len(turn)])
            if len(corners) >= 3 and _signed_area(corners) > 0:
                faces.append(_straighten(corners))
    return faces


def _inside(p: Point, polygon: list[Point]) -> bool:
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        if (a[1] > p[1]) != (b[1] > p[1]):
            x = a[0] + (p[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if p[0] < x:
                inside = not inside
    return inside


def _centre(polygon: list[Point]) -> Point:
    """The centre of a room's floor; the average of its corners if it is a line."""
    area = _signed_area(polygon)
    if abs(area) < EPS:
        n = len(polygon)
        return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)
    cx = cy = 0.0
    for a, b in zip(polygon, polygon[1:] + polygon[:1], strict=True):
        f = _cross(a, b)
        cx += (a[0] + b[0]) * f
        cy += (a[1] + b[1]) * f
    return (cx / (6 * area), cy / (6 * area))


def close_rooms(
    walls: list[Segment],
    rooms: list[tuple[str, list[Point]]],
    *,
    metres_per_pixel: float,
) -> list[tuple[str, list[Point]]]:
    """The rooms the walls close, each with the name read inside it.

    The walls decide the outline, because that is what the editor builds and
    measures; Claude's rooms only lend their names. A room Claude saw where the
    walls close nothing is kept as Claude read it, with its corners on the
    nearest wall ends.
    """
    tolerance = JOIN_METRES / metres_per_pixel
    doorway = DOORWAY_METRES / metres_per_pixel
    min_area = MIN_ROOM_AREA_M2 / metres_per_pixel**2
    min_width = MIN_ROOM_WIDTH_M / metres_per_pixel

    points, links = _graph(walls, doorway, tolerance)
    closed = [
        face
        for face in _faces(points, links)
        if len(face) >= 3
        and _signed_area(face) >= min_area
        and 2 * _signed_area(face) / _perimeter(face) >= min_width
    ]
    closed.sort(key=lambda face: (round(_centre(face)[1]), round(_centre(face)[0])))

    names: list[str] = [""] * len(closed)
    corners = [p for segment in walls for p in segment]
    as_read = []
    for name, outline in rooms:
        centre = _centre(outline)
        holders = [i for i, face in enumerate(closed) if _inside(centre, face)]
        if holders:
            smallest = min(holders, key=lambda i: _signed_area(closed[i]))
            names[smallest] = names[smallest] or name
            continue
        snapped = []
        for p in outline:
            near = min(corners, key=lambda c, p=p: _distance(c, p), default=None)
            on_corner = near is not None and _distance(near, p) <= tolerance
            snapped.append(near if on_corner else p)
        as_read.append((name, snapped))

    return list(zip(names, closed, strict=True)) + as_read
